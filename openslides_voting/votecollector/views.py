import json

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.translation import ugettext as _

from openslides.agenda.models import Item, Speaker
from openslides.assignments.models import AssignmentOption, AssignmentPoll
from openslides.core.exceptions import OpenSlidesError
from openslides.motions.models import MotionPoll
from openslides.users.models import User
from openslides.utils.auth import has_perm
from openslides.utils import views as utils_views
from openslides.utils.autoupdate import inform_changed_data

from . import rpc
from ..models import (
    AuthorizedVoters,
    Keypad,
    VotingController,
    MotionPollBallot,
    VotingShare,
    VotingToken,
)
from ..voting import AssignmentBallot, MotionBallot


class ValidationError(Exception):
    def __init__(self, msg):
        self.msg = msg


class ValidationView(utils_views.View):
    def dispatch(self, *args, **kwargs):
        try:
            return super().dispatch(*args, **kwargs)
        except ValidationError as e:
            return JsonResponse(e.msg, status=400)

    def decrypt_votecollector_message(self, message):
        # Use the SECRET_KEY to decrypt the message.
        # Raise a validationerror if the decryption fails!!
        return message

    def validate_input_data(self, data, voting_type, user):
        """
        returns the validated data or raises a ValidationError. The correct
        format is [{<vote>}, {<vote>}, ...], where vote is a dict with
        {
            value: <has to be there, but has to be checked separatly>,
            id: <keypad_number, not id!>,
            keypad: <keypad_instance>,
            bl: <keypad_battery_level>,
            token: <token_string>,
            token_instance: <token>,
        }
        id and bl are required if the voting type is votecollector and permitted
        if the type is not votecollector. The keypad is added during the validation.
        The token has to be given, if the voting type is token_based_electronic. The
        token_instance is queried during the validation. Also, the user has to have the
        'can_see_token_voting' permission.
        Additional fields in the dict are not cleared.
        If the voting type is not votecollector, the length of the list has to be one.
        """
        try:
            votes = json.loads(data.decode('utf-8'))
        except ValueError:
            raise ValidationError({'detail': 'The content is malformed.'})
        if not isinstance(votes, list):
            votes = [votes]

        if voting_type != 'votecollector' and len(votes) != 1:
            raise ValidationError({'detail': 'Just one vote has to be given'})

        for vote in votes:
            if not isinstance(vote, dict):
                raise ValidationError({'detail': 'All votes have to be a dict'})
            if 'value' not in vote:
                raise ValidationError({'detail': 'A vote value is missing'})

            if voting_type == 'votecollector':  # Check, if bl and id is given and valid
                if not 'bl' in vote or not 'id' in vote:
                    raise ValidationError({'detail': 'bl and id are necessary for the votecollector'})
                if not isinstance(vote['bl'], int) or not isinstance(vote['id'], int):
                    raise ValidationError({'detail': 'bl and id has to be int.'})
                try:
                    keypad = Keypad.objects.get(number=vote['id'])
                except Keypad.DoesNotExist:
                    raise ValidationError({
                        'detail': 'The keypad with id {} does not exist'.format(vote['id'])})
                vote['keypad'] = keypad
            elif voting_type == 'token_based_electronic':  # Check, if a valid token is given
                if not has_perm(user, 'openslides_voting.can_see_token_voting'):
                    raise ValidationError({'detail': 'The user does not have the permission to vote with tokens.'})
                token = vote.get('token')
                if not isinstance(token, str):
                    raise ValidationError({'detail': 'The token has to be a string.'})
                if len(token) > 128:
                    raise ValidationError({'detail': 'The token length must be lesser then 128.'})
                try:
                    token_instance = VotingToken.objects.get(token=token)
                except VotingToken.DoesNotExist:
                    raise ValidationError({'detail': 'The token is not valid.'})
                vote['token_instance'] = token_instance

        return votes


class SubmitVotes(ValidationView):
    http_method_names = ['post']

    def validate_simple_yna_votes(self, votes):
        """
        Checks, if all values are in ('Y', 'N' or 'A').
        """
        for vote in votes:
            value = vote['value']
            if not isinstance(value, str):
                raise ValidationError({'detail': 'Value has to be a string.'})
            if not value in ('Y', 'N', 'A'):
                raise ValidationError({'detail': 'Value has to be Y, N or A.'})

    def validate_and_format_votecollector_candidates_votes(self, votes, pollmethod, options):
        """
        Reformat the votes that come from the votecollector to match the
        internal structure. The pollmethod has to be 'yna' or 'yn'.
        """
        first_option_id = options[0].candidate.id
        for vote in votes:
            value = vote['value']
            if not isinstance(value, str):
                raise ValidationError({'detail': 'Value has to be a string.'})
            if not value in [s.upper() for s in pollmethod]:
                raise ValidationError({'detail': 'Value has to match the pollmethod {}.'.format(pollmethod)})
            vote['value'] = {
                first_option_id: value,
            }
        return votes


    def validate_candidates_votes(self, votes, pollmethod, options):
        """
        Check, if the votes values matches the given pollmethod. It can either be
        'yna' or 'yn'.
        The value has to be a dict with _every_ candidate index as key with 'Y', 'N'
        or 'A' as value (no 'A' for 'YN' method obviosly).
        """
        for vote in votes:
            value = vote['value']
            if not isinstance(value, dict):
                raise ValidationError({'detail': 'Value has to be a dict.'})
            for option in options:
                option_value = value.get(str(option.candidate.id))
                if not isinstance(option_value, str):
                    raise ValidationError({'detail': 'The option value (id {}) has the wrong format '.format(
                        option.candidate.id)})
                if option_value not in [s.upper() for s in pollmethod]:
                    raise ValidationError({'detail': 'The option value {} is wrong.'.format(
                        option_value)})

    @transaction.atomic()
    def post(self, request, poll_id, votecollector=False):
        """
        Takes requests for incomming votes. They should have the format given in
        self.validate_input_data. For a single vote, the list can be omitted.
        """
        poll_id = int(poll_id)
        vc = VotingController.objects.get()
        av = AuthorizedVoters.objects.get()

        # Check, if there is an active voting
        if not vc.is_voting:
            raise ValidationError({'detail': 'No currently active voting.'})

        # No voting for analog voting mode
        if av.type == 'analog':
            raise ValidationError({'detail': 'Analog voting does not support votes.'})

        # Only allow votecollector requests if the type is right and the other way around
        if votecollector and not av.type == 'votecollector':
            raise ValidationError({'detail': 'The type is not votecollector!'})
        if not votecollector and av.type == 'votecollector':
            raise ValidationError({'detail': 'Non votecollector requests are permitted!'})

        # check for valid poll_id
        if poll_id != vc.voting_target:
            raise ValidationError({'detail': 'The given poll id is not the current voting target.'})

        # get request content
        body = request.body
        if votecollector:
            body = self.decrypt_votecollector_message(body)
        votes = self.validate_input_data(body, av.type, request.user)

        if vc.voting_mode == 'MotionPoll':
            try:
                poll = MotionPoll.objects.get(id=poll_id)
            except MotionPoll.DoesNotExist:
                raise ValidationError({'detail': 'The MotionPoll does not exist.'})

            self.validate_simple_yna_votes(votes)

            ballot = MotionBallot(poll, vc.principle)
        elif vc.voting_mode == 'AssignmentPoll':
            try:
                poll = AssignmentPoll.objects.get(id=poll_id)
            except AssignmentPoll.DoesNotExist:
                raise ValidationError({'detail': 'The AssignmentPoll does not exist.'})

            # Here, just yna and yn methods are allowed:
            if poll.pollmethod not in ('yna', 'yn'):
                raise ValidationError({'detail': 'The pollmethod has to be yna or yn.'})

            # validate votes. For the votecollector the votes get formatted right.
            options = AssignmentOption.objects.filter(poll=poll_id).order_by('weight').all()
            if votecollector:
                votes = self.validate_and_format_votecollector_candidates_votes(
                    votes,
                    poll.pollmethod,
                    options)
            else:
                self.validate_candidates_votes(
                    votes,
                    poll.pollmethod,
                    options)

            ballot = AssignmentBallot(poll, vc.principle)
        else:
            raise ValidationError({'detail': 'The voting mode is neiher MotionPoll nor AssignmentPoll.'})

        # we can now operate for motions and assignment equally, because the logic is
        # encapsulated in the ballot objects
        result_token = 0
        result_vote = None
        if av.type in ('named_electronic', 'token_based_electronic'):
            vote = votes[0]
            user = None
            if av.type == 'named_electronic':
                user = request.user
                if user.id not in av.authorized_voters.keys():
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})
            else:
                token_instance = vote['token_instance']
                token_instance.delete()

                # Generate resultToken
                result_token = ballot.get_next_result_token()
                result_vote = vote['value']

            vc.votes_received += ballot.register_vote(vote['value'], voter=user, result_token=result_token)
        else:  # votecollector
            for vote in votes:
                # Mark keypad as in range and update battery level.
                keypad = vote['keypad']
                keypad.in_range = True
                keypad.battery_level = vote['bl']
                keypad.save()

                # Get delegate the keypad is assigned to.
                user = keypad.user
                if user is None:
                    continue
                    # TODO: Design decision. Keypads can vote, if they are not connected to users.
                    # Should we allow this, or not. If not, should we do it silent (like now with
                    # the continue statement) or raise an error?
                    # Info: Adapt this decision also in the CandidateSubmit-View.
                    #raise ValidationError({
                    #    'detail': 'The user with the keypad id {} does not exist'.format(keypad.id)})

                # Write ballot.
                vc.votes_received += ballot.register_vote(vote['value'], voter=user)
        vc.save()

        return JsonResponse({
            'result_token': result_token,
            'result_vote': result_vote})


class SubmitCandidates(ValidationView):
    http_method_names = ['post']

    def validate_candidates_votes(self, votes, options):
        """
        Validates, that the vote values are integers with 0 < value <= len(options).
        replaves this index with the actual candidate id.
        """
        for vote in votes:
            value = vote['value']
            try:
                value = int(value)
            except:
                raise ValidationError({'detail': 'Value has to be an int.'})
            if value > len(options) or value <= 0:
                raise ValidationError({'detail': 'Value has to be less or equal to {}.'.format(len(options))})

            vote['value'] = str(options[value - 1].candidate.id)  # save the actual candidate id
        return votes

    @transaction.atomic()
    def post(self, request, poll_id, votecollector=False):
        """
        Takes requests for incomming votes for candidates. They should have the format
        given in self.validate_input_data with the matching format for value (the pollmethod).
        For a single vote, the list can be omitted.
        Note: The values for the candidates are NOT the IDs. Its the index started by 1, if
        you put all candidates ordered by their weight in a straight order.
        """
        poll_id = int(poll_id)
        try:
            poll = AssignmentPoll.objects.get(id=poll_id)
        except AssignmentPoll.DoesNotExist:
            raise ValidationError({'detail': 'The AssignmentPoll does not exist.'})

        vc = VotingController.objects.get()
        av = AuthorizedVoters.objects.get()

        # Check, if there is an active voting
        if not vc.is_voting:
            raise ValidationError({'detail': 'No currently active voting.'})

        # No voting for analog voting mode
        if av.type == 'analog':
            raise ValidationError({'detail': 'Analog voting does not support votes.'})

        # Only allow votecollector requests if the type is right and the other way around
        if votecollector and not av.type == 'votecollector':
            raise ValidationError({'detail': 'The type is not votecollector!'})
        if not votecollector and av.type == 'votecollector':
            raise ValidationError({'detail': 'Non votecollector requests are permitted!'})

        # check for valid poll_id
        if poll_id != vc.voting_target:
            raise ValidationError({'detail': 'The given poll id is not the current voting target.'})

        # Here, just the votes methods is allowed:
        if poll.pollmethod != 'votes':
            raise ValidationError({'detail': 'The pollmethod has to be votes.'})

        options = AssignmentOption.objects.filter(poll=poll_id).order_by('weight').all()
        ballot = AssignmentBallot(poll)

        # get request content
        body = request.body
        if votecollector:
            body = self.decrypt_votecollector_message(body)
        votes = self.validate_input_data(body, av.type, request.user)
        votes = self.validate_candidates_votes(votes, options)

        result_token = 0
        result_vote = None
        if av.type in ('named_electronic', 'token_based_electronic'):
            vote = votes[0]
            user = None
            if av.type == 'named_electronic':
                user = request.user
                if user.id not in av.authorized_voters.keys():
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})
            else:
                token_instance = vote['token_instance']
                token_instance.delete()

                # Generate resultToken
                result_token = ballot.get_next_result_token()
                result_vote = vote['value']

            vc.votes_received += ballot.register_vote(
                vote['value'],
                voter=user,
                principle=vc.principle,
                result_token=result_token)
        else:  # votecollector
            keypad_set = set()
            for vote in votes:
                # Mark keypad as in range and update battery level.
                keypad = vote['keypad']
                keypad.in_range = True
                keypad.battery_level = vote['bl']
                keypad.save()

                # Get delegate the keypad is assigned to.
                user = keypad.user
                if user is None:
                    continue
                    #raise ValidationError({
                    #    'detail': 'The user with the keypad id {} does not exist'.format(keypad.id)})
                if user.id not in av.authorized_voters.keys():
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})

                # Write ballot.
                candidate_id = options[vote['value'] - 1].candidate_id
                ballots_created = ballot.register_vote(
                    candidate_id,
                    voter=user,
                    principle=vc.principle)
                if ballots_created > 0:
                    keypad_set.add(keypad.id)
                    vc.votes_received += ballots_created

        vc.save()
        return JsonResponse({
            'result_token': result_token,
            'result_vote': result_vote})

"""
class VotingCallbackView(utils_views.View):
    http_method_names = ['post']

    def post(self, request, poll_id, keypad_id):
        # Get keypad.
        try:
            keypad = Keypad.objects.get(number=keypad_id)
        except Keypad.DoesNotExist:
            return None

        # Mark keypad as in range and update battery level.
        keypad.in_range = True
        keypad.battery_level = request.POST.get('battery', -1)
        # Do not auto update here to improve performance.
        keypad.save(skip_autoupdate=True)
        return keypad


class VoteCallback(VotingCallbackView):
    @transaction.atomic
    def post(self, request, poll_id, keypad_id):
        keypad = super().post(request, poll_id, keypad_id)
        if keypad is None:
            return HttpResponse(_('Vote rejected'))

        # Validate vote value.
        value = request.POST.get('value')
        if value not in ('Y', 'N', 'A'):
            return HttpResponse(_('Vote invalid'))

        # Save vote.
        vc = VotingController.objects.get()
        model = MotionPoll if vc.voting_mode == 'MotionPoll' else AssignmentPoll
        try:
            poll = model.objects.get(id=poll_id)
        except model.DoesNotExist:
            return HttpResponse(_('Vote rejected'))

        if vc.voting_mode == 'MotionPoll':
            ballot = MotionBallot(poll)
            if ballot.register_vote(keypad_id, value) == 0:
                return HttpResponse(_('Vote rejected'))

        # Update votecollector.
        vc.votes_received = request.POST.get('votes', 0)
        vc.voting_duration = request.POST.get('elapsed', 0)
        vc.save()

        return HttpResponse(_('Vote submitted'))



class CandidateCallback(VotingCallbackView):
    @transaction.atomic()
    def post(self, request, poll_id, keypad_id):
        keypad = super().post(request, poll_id, keypad_id)
        if keypad is None:
            return HttpResponse(_('Vote rejected'))

        # Get assignment poll.
        try:
            poll = AssignmentPoll.objects.get(id=poll_id)
        except AssignmentPoll.DoesNotExist:
            return HttpResponse(_('Vote rejected'))

        # Validate vote value.
        try:
            key = int(request.POST.get('value'))
        except ValueError:
            return HttpResponse(_('Vote invalid'))
        if key < 0 or key > 9:
            return HttpResponse(_('Vote invalid'))

        # Get the elected candidate.
        candidate = None
        if key > 0 and key <= poll.assignment.related_users.all().count():
            candidate = AssignmentOption.objects.filter(poll=poll_id).order_by('weight').all()[key - 1].candidate

        # TODO: Save candidate vote.

        # Update votingcontroller.
        vc = VotingController.objects.get()
        vc.votes_received = request.POST.get('votes', 0)
        vc.voting_duration = request.POST.get('elapsed', 0)
        vc.save()

        return HttpResponse(_('Vote submitted'))


class SpeakerCallback(VotingCallbackView):
    @transaction.atomic()
    def post(self, request, item_id, keypad_id):
        keypad = super().post(request, item_id, keypad_id)
        if keypad is None:
            return HttpResponse(_('Keypad not registered'))

        # Anonymous users cannot be added or removed from the speaker list.
        if keypad.user is None:
            return HttpResponse(_('User unknown'))

        # Get agenda item.
        try:
            item = Item.objects.get(id=item_id)
        except MotionPoll.DoesNotExist:
            return HttpResponse(_('No agenda item selected'))

        # Add keypad user to the speaker list.
        value = request.POST.get('value')
        if value == 'Y':
            try:
                # Add speaker to "next speakers" if not already on the list (begin_time=None).
                Speaker.objects.add(keypad.user, item)
            except OpenSlidesError:
                # User is already on the speaker list.
                pass
            content = _('Added to        speakers list')
        # Remove keypad user from the speaker list.
        elif value == 'N':
            # Remove speaker if on "next speakers" list (begin_time=None, end_time=None).
            queryset = Speaker.objects.filter(user=keypad.user, item=item, begin_time=None, end_time=None)
            try:
                # We assume that there aren't multiple entries because this
                # is forbidden by the Manager's add method. We assume that
                # there is only one speaker instance or none.
                speaker = queryset.get()
            except Speaker.DoesNotExist:
                content = _('Does not exist  on speakers list')
            else:
                speaker.delete()
                content = _('Removed from    speakers list')
        else:
            content = _('Invalid entry')
        return HttpResponse(content)


class Keypads(utils_views.View):
    http_method_names = ['post']

    def post(self, request):
        # Load json list from request body.
        votes = json.loads(request.body.decode('utf-8'))
        keypads = []
        for vote in votes:
            keypad_id = vote['id']
            try:
                keypad = Keypad.objects.get(number=keypad_id)
            except Keypad.DoesNotExist:
                continue

            # Mark keypad as in range and update battery level.
            keypad.in_range = True
            keypad.battery_level = vote['bl']
            keypad.save(skip_autoupdate=True)
            keypads.append(keypad)

        # Trigger auto-update.
        inform_changed_data(keypads)

        return HttpResponse()


class KeypadCallback(VotingCallbackView):
    @transaction.atomic()
    def post(self, request, poll_id=0, keypad_id=0):
        keypad = super().post(request, poll_id, keypad_id)
        if keypad:
            inform_changed_data(keypad)
        return HttpResponse()
"""
