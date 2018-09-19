import base64
import hmac
import hashlib
import json

from django.db import transaction
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.translation import ugettext as _

from openslides.agenda.models import Item, Speaker
from openslides.assignments.models import AssignmentOption, AssignmentPoll
from openslides.core.exceptions import OpenSlidesError
from openslides.motions.models import MotionPoll
from openslides.utils.auth import has_perm
from openslides.utils import views as utils_views
from openslides.utils.autoupdate import inform_changed_data

from ..models import (
    AuthorizedVoters,
    Keypad,
    VotingController,
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

    def decode_votecollector_message(self, message):
        """
        Authenticates and decodes a votecollector message. Uses HMAC authentication.
        :param message: json dictionary with keys 'message' and 'hmac'
        :return: dictionary value of 'message'
        """
        if isinstance(message, bytes):
            message = message.decode('utf-8')
        try:
            d = json.loads(message)
            # Create HMAC hash of the message.
            key = bytes(settings.SECRET_KEY, 'utf-8')
            digest = hmac.new(key, bytes(d['message'], 'utf-8'), hashlib.sha256).digest()
            hash = base64.b64encode(digest).decode('utf-8')
            # hash must match the hmac value sent.
            if hash != d['hmac']:
                raise ValidationError({'detail': 'HMAC authentication failed.'})
            return d['message']
        except (ValueError, TypeError, KeyError):
            raise ValidationError({'detail': 'The content is malformed.'})

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
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        try:
            votes = json.loads(data)
        except ValueError:
            raise ValidationError({'detail': 'The content is malformed.'})
        if not isinstance(votes, list):
            votes = [votes]

        if not voting_type.startswith('votecollector') and len(votes) != 1:
            raise ValidationError({'detail': 'Just one vote has to be given'})

        for vote in votes:
            if not isinstance(vote, dict):
                raise ValidationError({'detail': 'All votes have to be a dict'})
            if 'value' not in vote:
                raise ValidationError({'detail': 'A vote value is missing'})

            if voting_type.startswith('votecollector'):
                # Check, if bl, id and sn is given and valid.
                if not {'bl', 'id', 'sn'}.issubset(vote):
                    raise ValidationError({'detail': 'bl, id and sn are necessary for the votecollector'})
                if not isinstance(vote['bl'], int) or not isinstance(vote['id'], int):
                    raise ValidationError({'detail': 'bl and id has to be int.'})
                try:
                    keypad = Keypad.objects.get(number=vote['id'])
                except Keypad.DoesNotExist:
                    # Keypad might have been deleted after voting has started.
                    keypad = None
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
                    raise ValidationError({'detail': 'The voting token is not valid.'})
                vote['token_instance'] = token_instance

        return votes

    def update_keypads_from_votes(self, votes, voting_type):
        """
        Updates the keypds from votes. The voting type has to be a VoteCollector one.
        The votes has to be validated first.
        """
        if voting_type.startswith('votecollector'):
            keypads = []
            for vote in votes:
                keypad = vote['keypad']
                # Mark keypad as in range and update battery level.
                if keypad:
                    keypad.in_range = True
                    keypad.battery_level = vote['bl']
                    keypad.save(skip_autoupdate=True)
                    keypads.append(keypad)

            # Trigger auto-update for keypads.
            inform_changed_data(keypads)


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
        Takes requests for incoming votes. They should have the format given in
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
        if votecollector and not av.type.startswith('votecollector'):
            raise ValidationError({'detail': 'The type is not votecollector!'})
        if not votecollector and av.type.startswith('votecollector'):
            raise ValidationError({'detail': 'Non votecollector requests are permitted!'})

        # check for valid poll_id
        if poll_id != vc.voting_target:
            raise ValidationError({'detail': 'The given poll id is not the current voting target.'})

        # get request content
        body = request.body
        if votecollector:
            body = self.decode_votecollector_message(body)
        votes = self.validate_input_data(body, av.type, request.user)
        self.update_keypads_from_votes(votes, av.type)

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
                if str(user.id) not in av.authorized_voters:
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})
            else:
                token_instance = vote['token_instance']
                token_instance.delete()

                # Generate resultToken
                result_token = ballot.get_next_result_token()
                result_vote = vote['value']

            vc.votes_received += ballot.register_vote(vote['value'], voter=user, result_token=result_token)
        else:  # a votecollector type
            for vote in votes:
                keypad = vote['keypad']
                user = None
                if av.type in ('votecollector', 'votecollector_secret', 'votecollector_pseudo_secret'):  # vc with user
                    # Get delegate the keypad is assigned to.
                    if keypad:
                        user = keypad.user
                    if user is None or str(user.id) not in av.authorized_voters:
                        # no or no valid user, skip the vote
                        continue

                # Write ballot.
                vc.votes_received += ballot.register_vote(vote['value'], voter=user, device=vote['sn'])
        vc.save()

        return JsonResponse({
            'result_token': result_token,
            'result_vote': result_vote})


class SubmitCandidates(ValidationView):
    http_method_names = ['post']

    def validate_candidates_votes(self, votes, options, range_exception, open_posts):
        """
        Some more types of vote values are accepted here:
        - A simple 'A' or 'N' for abstain or No. You can give an empty list for abstian as well.
        - A list with candidate indices. They should be unique. Indices are integers with
          0 < i <= len(options). Replaces these indeicesx with the actual candidate ids in string.
        - A single digit: Will be converted to [<id>] and the rule above applies.
        """
        for vote in votes:
            value = vote['value']
            # for the votecollector single digits are allowed
            if isinstance(value, str):
                try:
                    value = [int(value)]
                except ValueError:
                    pass

            # check for 'A', 'N' or a list of indices
            if isinstance(value, list):
                value_set = set(value)
                if len(value_set) != len(value):  # someone has votes for the same candidate multiple times
                    raise ValidationError({'detail': 'You cannot give more than one vote per candidate.'})

                if len(value) > open_posts:
                    raise ValidationError({'detail': 'You cannot cast more votes than candidates available.'})

                if len(value) == 0:
                    vote['value'] = 'A'
                else:
                    for index in value:
                        if not isinstance(index, int):
                            raise ValidationError({'detail': 'An index has to be int.'})
                        if index == 0:
                            vote['value'] = 'A'  # abstain
                        if index > len(options) or index < 0:
                            vote['value'] = 'invalid'  # invalid vote
                            if range_exception:
                                raise ValidationError({'detail': 'Value has to be less or equal to {}.'.format(len(options))})
                        else:
                            # map the actual candidate ids stringified
                            vote['value'] = [str(options[i - 1].candidate.id) for i in value]

            elif isinstance(value, str):
                if value not in ('A', 'N'):
                    raise ValidationError({'detail': 'Value has to be a list of indices, "A" or "N".'})
            else:
                raise ValidationError({'detail': 'Value has to be a list of indices, "A" or "N".'})
        return votes

    @transaction.atomic()
    def post(self, request, poll_id, votecollector=False):
        """
        Takes requests for incomming votes for candidates. They should have the format
        given in self.validate_input_data with the matching format for value (the pollmethod).
        For a single vote, the list can be omitted.
        The actual vote format can be determined by reading the docstrin from `validate_candidate_votes`.
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
        if votecollector and not av.type.startswith('votecollector'):
            raise ValidationError({'detail': 'The type is not votecollector!'})
        if not votecollector and av.type.startswith('votecollector'):
            raise ValidationError({'detail': 'Non votecollector requests are permitted!'})

        # check for valid poll_id
        if poll_id != vc.voting_target:
            raise ValidationError({'detail': 'The given poll id is not the current voting target.'})

        # Here, just the votes methods is allowed:
        if poll.pollmethod != 'votes':
            raise ValidationError({'detail': 'The pollmethod has to be votes.'})

        options = AssignmentOption.objects.filter(poll=poll_id).order_by('weight').all()
        ballot = AssignmentBallot(poll, vc.principle)

        # get request content
        body = request.body
        if votecollector:
            body = self.decode_votecollector_message(body)
        votes = self.validate_input_data(body, av.type, request.user)
        votes = self.validate_candidates_votes(votes, options, not votecollector, poll.assignment.open_posts)
        self.update_keypads_from_votes(votes, av.type)

        result_token = 0
        result_vote = None
        if av.type in ('named_electronic', 'token_based_electronic'):
            vote = votes[0]
            user = None
            if av.type == 'named_electronic':
                user = request.user
                if str(user.id) not in av.authorized_voters:
                    raise ValidationError({'detail': 'The user is not authorized to vote.'})
            else:
                token_instance = vote['token_instance']
                token_instance.delete()

                # Generate resultToken
                result_token = ballot.get_next_result_token()
                result_vote = vote['value']
            vc.votes_received += ballot.register_vote(vote['value'], voter=user, result_token=result_token)
        else:  # a votecollector type
            for vote in votes:
                keypad = vote['keypad']
                user = None
                if av.type in ('votecollector', 'votecollector_secret', 'votecollector_pseudo_secret'):  # vc with user
                    # Get delegate the keypad is assigned to.
                    if keypad:
                        user = keypad.user
                    if user is None or str(user.id) not in av.authorized_voters:
                        # no or no valid user, skip the vote
                        continue

                # Write ballot.
                vc.votes_received += ballot.register_vote(vote['value'], voter=user, device=vote['sn'])

        vc.save()
        return JsonResponse({
            'result_token': result_token,
            'result_vote': result_vote})


class SubmitSpeaker(ValidationView):
    http_method_names = ['post']

    @transaction.atomic()
    def post(self, request, item_id, keypad_number):
        item_id = int(item_id)

        # Validate voting mode.
        vc = VotingController.objects.get()
        if not vc.is_voting:
            return HttpResponse(_('No active voting'))

        if vc.voting_mode != 'Item' or item_id != vc.voting_target:
            return HttpResponse(_('Invalid voting  mode or target'))

        # Authenticate request.
        self.decode_votecollector_message(request.POST.get('auth'))

        # Get keypad.
        try:
            keypad = Keypad.objects.get(number=keypad_number)
        except Keypad.DoesNotExist:
            return HttpResponse(_('Keypad not      registered'))

        # Mark keypad as in range and update battery level.
        keypad.in_range = True
        keypad.battery_level = request.POST.get('battery', -1)
        keypad.save()

        # Anonymous users cannot be added or removed from the speaker list.
        if keypad.user is None:
            return HttpResponse(_('User unknown'))

        # Get agenda item.
        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            return HttpResponse(_('Invalid agenda  item'))

        value = request.POST.get('value')
        if value == 'Y':
            # Add keypad user to "next speakers" if not already on the list (begin_time=None).
            try:
                Speaker.objects.add(keypad.user, item)
            except OpenSlidesError:
                # User is already on the speaker list.
                pass
            content = _('Added to        speakers list')
        elif value == 'N':
            # Remove keypad user if on "next speakers" list (begin_time=None, end_time=None).
            speaker = Speaker.objects.filter(user=keypad.user, item=item, begin_time=None, end_time=None).first()
            if speaker:
                speaker.delete()
                content = _('Removed from    speakers list')
            else:
                content = _('Does not exist  on speakers list')
        else:
            content = _('Invalid entry')

        # Return response with content to be displayed on keypad.
        # Content contains extra whitespace for formatting purposes, e.g. to force a linefeed.
        # Engage keypads have a line width of 16 characters.
        return HttpResponse(content)


class SubmitKeypads(ValidationView):
    http_method_names = ['post']

    @transaction.atomic()
    def post(self, request):
        # Validate voting mode.
        vc = VotingController.objects.get()
        if not vc.is_voting:
            raise ValidationError({'detail': 'No currently active voting.'})

        if vc.voting_mode != 'ping':
            raise ValidationError({'detail': 'Invalid voting mode.'})

        # Get request content.
        body = self.decode_votecollector_message(request.body)

        # Validate marks keypads as in range and updates battery levels.
        votes = self.validate_input_data(body, 'votecollector', request.user)
        self.update_keypads_from_votes(votes, 'votecollector')

        return HttpResponse()
