import json

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.translation import ugettext as _

from openslides.agenda.models import Item, Speaker
from openslides.assignments.models import AssignmentOption, AssignmentPoll
from openslides.core.exceptions import OpenSlidesError
from openslides.motions.models import MotionPoll
from openslides.utils import views as utils_views
from openslides.utils.autoupdate import inform_changed_data

from . import rpc
from ..models import AuthorizedVoters, Keypad, VotingController, MotionPollBallot, VotingShare
from ..voting import MotionBallot


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



class SubmitVotes(ValidationView):
    http_method_names = ['post']

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
        # TODO: Isn't this redundant? Why does the users/votecollector have to give the
        # poll_id, if the id of the current voting is saved in the votingcontroller
        if poll_id != vc.voting_target:
            raise ValidationError({'detail': 'The given poll id is not the current voting target.'})

        # get request content
        body = request.body
        if votecollector:
            body = self.decrypt_message(body)
        votes = self.validate_input_data(body, votecollector)

        if vc.voting_mode == 'MotionPoll':
            try:
                poll = MotionPoll.objects.get(id=poll_id)
            except MotionPoll.DoesNotExist:
                raise ValidationError({'detail': 'The MotionPoll does not exist.'})

            # Get ballot instance.
            ballot = MotionBallot(poll)

            if av.type in ('named_electronic', 'token_based_electronic'):
                user = None
                if av.type == 'named_electronic':
                    user = request.user

                if user.id not in av.authorized_voters:
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})

                vote = votes[0]
                vc.votes_received += ballot.register_vote(vote['value'], voter=user)
                vc.save()
            else:  # votecollector
                keypad_set = set()
                for vote in votes:
                    # Mark keypad as in range and update battery level.
                    keypad = vote['keypad']
                    keypad.in_range = True
                    keypad.battery_level = vote['bl']
                    keypad.save()

                    # Get delegate user the keypad is assigned to.
                    try:
                        user = User.objects.get(keypad__number=keypad_id)
                    except User.DoesNotExist:
                        raise ValidationError({
                            'detail': 'The user with the keypad id {} does not exist'.format(keypad.id)})
                    if user.id not in av.authorized_voters:
                        raise ValidationError({'detail': 'The user is not authorized to vote.'})

                    # Write ballot.
                    ballots_created = ballot.register_vote(vote['value'], voter=user)
                    if ballots_created > 0:
                        keypad_set.add(keypad.id)
                        vc.votes_received += ballots_created
                        vc.save()

        elif vc.voting_mode == 'AssignmentPoll':  # TODO
            pass
        else:
            raise ValidationError({'detail': 'The voting mode is neiher MotionPoll nor AssignmentPoll.'})

        return HttpResponse()

    def validate_input_data(self, data, votecollector):
        """
        returns the validated data or raises a ValidationError. The correct
        format is [{<vote>}, {<vote>}, ...], where vote is a dict with
        {
            value: 'Y', 'N' or 'A',
            id: <keypad_id>,
            keypad: <keypad_instance>,
            bl: <keypad_battery_level>
        }
        id and bl are required if votecollector is true and permitted if votecollector
        is False.
        Additional fields in the dict are not cleared.
        If votecollector is False, the length of the list has to be one.
        """
        try:
            votes = json.loads(data.decode('utf-8'))
        except ValueError:
            raise ValidationError({'detail': 'The content is malformed.'})
        if not isinstance(votes, list):
            votes = [votes]

        if not votecollector and len(votes) != 1:
            raise ValidationError({'detail': 'Just one vote has to be given'})

        for vote in votes:
            if not isinstance(vote, dict):
                raise ValidationError({'detail': 'All votes have to be a dict'})
            value = vote.get('value')
            if not isinstance(value, str):
                raise ValidationError({'detail': 'Value has to be a string.'})
            if not value in ('Y', 'N', 'A'):
                raise ValidationError({'detail': 'Value has to be Y, N or A.'})
            if votecollector:
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
        return votes


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


class Candidates(utils_views.View):
    http_method_names = ['post']

    @transaction.atomic()
    def post(self, request, poll_id):
        # Get assignment poll.
        try:
            poll = AssignmentPoll.objects.get(id=poll_id)
        except AssignmentPoll.DoesNotExist:
            return HttpResponse('')

        # Load json list from request body.
        votes = json.loads(request.body.decode('utf-8'))
        candidate_count = poll.assignment.related_users.all().count()
        keypad_set = set()
        connections = []
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

            # Validate vote value.
            try:
                value = int(vote['value'])
            except ValueError:
                continue
            if value < 0 or value > 9:
                # Invalid candidate number.
                continue

            # Get the selected candidate.
            candidate_id = None
            if 0 < value <= candidate_count:
                candidate_id = AssignmentOption.objects.filter(poll=poll_id).order_by('weight').all()[value - 1].candidate_id

            # TODO: Save candidates

        return HttpResponse()


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
