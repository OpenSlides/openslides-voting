import random

from decimal import Decimal

from django.db.models import Prefetch
from django.http.response import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views import View

from openslides.agenda.models import Item
from openslides.assignments.models import Assignment, AssignmentOption, AssignmentPoll
from openslides.core.config import config
from openslides.core.models import Projector, Countdown
from openslides.motions.models import Category, Motion, MotionPoll
from openslides.users.models import User
from openslides.utils.auth import has_perm
from openslides.utils.autoupdate import inform_deleted_data
from openslides.utils.rest_api import (
    detail_route,
    ModelViewSet,
    ValidationError,
    list_route,
    Response
)

from .votecollector import rpc

from .access_permissions import (
    permission_required,
    AssignmentAbsenteeVoteAccessPermissions,
    AssignmentPollBallotAccessPermissions,
    AssignmentPollTypeAccessPermissions,
    AttendanceLogAccessPermissions,
    AuthorizedVotersAccessPermissions,
    KeypadAccessPermissions,
    MotionAbsenteeVoteAccessPermissions,
    MotionPollBallotAccessPermissions,
    MotionPollTypeAccessPermissions,
    VotingControllerAccessPermissions,
    VotingProxyAccessPermissions,
    VotingPrincipleAccessPermissions,
    VotingShareAccessPermissions,
    VotingTokenAccessPermissions
)
from .models import (
    AssignmentAbsenteeVote,
    AssignmentPollBallot,
    AssignmentPollType,
    AttendanceLog,
    AuthorizedVoters,
    Keypad,
    MotionAbsenteeVote,
    MotionPollBallot,
    MotionPollType,
    VotingController,
    VotingPrinciple,
    VotingProxy,
    VotingShare,
    VotingToken
)
from .voting import (
    AssignmentBallot,
    MotionBallot,
    find_authorized_voter,
    get_admitted_delegates,
)


class PermissionMixin:
    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class AuthorizedVotersViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AuthorizedVotersAccessPermissions()
    queryset  = AuthorizedVoters.objects.all()


class VotingControllerViewSet(PermissionMixin, ModelViewSet):
    access_permissions = VotingControllerAccessPermissions()
    queryset = VotingController.objects.all()

    prompt_key = 'a016f7ecaf2147b2b656c6edf45c24ef'
    countdown_key = '134ddb26831743d586cbfa17e4712be9'

    def check_view_permissions(self):
        """
        Just allow listing. The one and only votingcontroller is created
        during migrations.
        """
        if self.action in ('list', 'retrieve', 'start_motion', 'start_assignment',
                'start_list_speakers', 'results_motion_votes', 'results_assignment_votes',
                'clear_motion_votes', 'clear_assignment_votes', 'stop',
                'update_votecollector_device_status', 'ping_votecollector'):
            return self.get_access_permissions().check_permissions(self.request.user)
        return False

    @detail_route(['post'])
    def start_motion(self, request, **kwargs):
        """
        Starts a voting for a motion poll. The poll id has to be given as the only argument:
        {poll_id: <poll_id>}
        """
        return self.start_voting(request, MotionPoll)

    @detail_route(['post'])
    def start_assignment(self, request, **kwargs):
        """
        Starts an election for an assignment poll. The poll id has to be
        given as the only argument: {poll_id: <poll_id>}
        """
        return self.start_voting(request, AssignmentPoll)

    def start_voting(self, request, model):
        vc = self.get_object()
        poll, poll_id = self.get_request_object(request, model)

        # get voting principle and type from motion or assignment
        principle = None
        voting_type = None
        # Get candidate name (if is an election with one candidate only)
        candidate_str = ''
        # projector message and images
        projector_message = _(config['voting_start_prompt'])
        projector_yes = '<img src="/static/img/button-yes.png">'
        projector_no = '<img src="/static/img/button-no.png">'
        projector_abstain = '<img src="/static/img/button-abstain.png">'
        if type(poll) == MotionPoll:
            try:
                principle = VotingPrinciple.objects.get(motions=poll.motion)
            except VotingPrinciple.DoesNotExist:
                pass

            try:
                voting_type = MotionPollType.objects.get(poll=poll).type
            except MotionPollType.DoesNotExist:
                voting_type = config['voting_default_voting_type']

            if voting_type == 'votecollector':
                if 'Interact' in vc.device_status:
                    projector_abstain = '2 = '
                elif 'Reply' in vc.device_status:
                    projectoryes = '1 = '
                    projector_no = '2 = '
                    projector_abstain = '3 = '
                projector_message += '&nbsp;' + \
                '<span class="nobr">' + projector_yes + _('Yes') + '</span>&nbsp;' + \
                '<span class="nobr">' + projector_no + _('No') + '</span>&nbsp;' + \
                '<span class="nobr">' + projector_abstain + _('Abstain') + '</span>'

            votecollector_mode = 'YesNoAbstain'
            votecollector_resource = '/vote/'

            absentee_ballots_created = MotionBallot(poll, principle).create_absentee_ballots()
        elif type(poll) == AssignmentPoll:
            try:
                principle = VotingPrinciple.objects.get(assignments=poll.assignment)
            except VotingPrinciple.DoesNotExist:
                pass

            try:
                voting_type = AssignmentPollType.objects.get(poll=poll).type
            except AssignmentPollType.DoesNotExist:
                voting_type = config['voting_default_voting_type']

            options = AssignmentOption.objects.filter(poll=poll).order_by('weight')
            # check, if the pollmethod is supported by the votecollector
            # If so, calculate the projector message for the voting prompt
            if voting_type == 'votecollector':
                if poll.pollmethod == 'yn' or (poll.pollmethod == 'yna' and options.count() is not 1):
                    raise ValidationError({'detail':
                        'The votecollector does not support the pollmethod {} (with {} candidates).'.format(
                            poll.pollmethod,
                            options.count())})

                if 'Interact' in vc.device_status:
                    projector_abstain = '2 = '
                elif 'Reply' in vc.device_status:
                    projectoryes = '1 = '
                    projector_no = '2 = '
                    projector_abstain = '3 = '

                # calculate the candidate string
                if poll.pollmethod == 'yna':
                    candidate = str(options.all()[0].candidate)
                    projector_message += '&nbsp;' + \
                        '<span class="nobr">' + projector_yes + _('Yes') + '</span>&nbsp;' + \
                        '<span class="nobr">' + projector_no + _('No') + '</span>&nbsp;' + \
                        '<span class="nobr">' + projector_abstain + _('Abstain') + '</span>' + \
                        '<div class="spacer candidate">' + candidate + '</div>'

                    votecollector_mode = 'YesNoAbstain'
                    votecollector_resource = '/vote/'
                else:  # votes
                    projector_message += '<div><ul class="columns" data-columns="3">'
                    for index, option in enumerate(options.all()):
                        projector_message += \
                                '<li><span class="key">' + str(index + 1) + '</span>' + \
                                '<span class="candidate">' + str(option.candidate) + '</span></li>'
                    projector_message += '<li><span class="key">0</span><span class="candidate">' + \
                        _('Abstain') + '</span></li></ul></div>'

                    if options.count() < 10:
                        votecollector_mode = 'SingleDigit'
                    else:
                        votecollector_mode = 'MultiDigit'
                    votecollector_resource = '/candidate/'

            absentee_ballots_created = AssignmentBallot(poll).create_absentee_ballots()
        else:
            raise ValidationError({'detail': 'Not supported type {}.'.format(type(poll))})

        if voting_type == 'votecollector':
            if not config['voting_enable_votecollector']:
                raise ValidationError({'detail': 'The VoteCollector is not enabled'})

            # Stop any active voting no matter what mode.
            self.force_stop_active_votecollector()

            url = rpc.get_callback_url(request) + votecollector_resource
            url += '%s/' % poll_id

            print(votecollector_mode)

            try:
                vc.votes_count, vc.device_status = rpc.start_voting(votecollector_mode, url)
            except rpc.VoteCollectorError as e:
                raise ValidationError({'detail': e.value})

            # Limit voters count to length of admitted delegates list.
            vc.votes_count, admitted_delegates = get_admitted_delegates(principle, keypad=True)

        elif voting_type == 'named_electronic':
            # Limit voters count to length of admitted delegates list.
            vc.votes_count, admitted_delegates = get_admitted_delegates(principle)

        else:  # 'token_based_electronic'
            admitted_delegates = None
            vc.votes_count = 0  # We do not know, how many votes will come..

        vc.voting_mode = model.__name__
        vc.voting_target = poll_id
        vc.votes_received = absentee_ballots_created
        vc.is_voting = True
        vc.principle = principle
        vc.save()

        # Update AuthorizedVoter object
        if type(poll) == MotionPoll:
            AuthorizedVoters.set_voting(admitted_delegates, voting_type, motion_poll=poll)
        else:
            AuthorizedVoters.set_voting(admitted_delegates, voting_type, assignment_poll=poll)

        # Add projector message
        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/prompt',
            'message': projector_message,
            'stable': True
        }

        # Auto start countdown and add it to projector.
        if config['voting_auto_countdown']:
            # Use countdown 2 since 1 is reserved for speakers list.
            countdown, created = Countdown.objects.get_or_create(
                pk=2, description=_('Poll is open'),
                defaults={'default_time': config['projector_default_countdown'],
                          'countdown_time': config['projector_default_countdown']}
            )
            if not created:
                countdown.control(action='reset')
            countdown.control(action='start')
            projector.config[self.countdown_key] = {
                'name': 'core/countdown',
                'id': 2,
                'stable': True
            }
        projector.save(information={'voting_prompt': True})

        return Response()

    @detail_route(['post'])
    def start_speaker_list(self,request, **kwargs):
        """
        Starts a voting for the speakers list. Give the item id by:
        {item_id: item_id}
        """
        vs = self.get_object()
        item, item_id = self.get_request_object(request, Item, attr_name='item_id')

        self.force_stop_active_votecollector()
        url = rpc.get_callback_url(request) + '/speaker/' + str(item_id) + '/'

        try:
            vc.votes_count, self.vc.device_status = rpc.start_voting('SpeakerList', url)
        except rpc.VoteCollectorError as e:
            raise ValidationError({'detail': e.value})

        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/icon',
            'stable': True
        }
        projector.save(information={'voting_prompt': True})

        self.vc.voting_mode = 'SpeakerList'
        self.vc.voting_target = item_id
        self.vc.votes_received = 0
        self.vc.is_voting = True
        self.vc.save()

        return Response()

    @detail_route(['post'])
    def results_motion_votes(self, request, **kwargs):
        """
        Get results from a motion poll: {poll_id: <poll_id>}.
        """
        return self.results_votes(request, MotionPoll)

    @detail_route(['post'])
    def results_assignment_votes(self, request, **kwargs):
        """
        Get results from a given assignment poll: {poll_id: <poll_id>}.
        """
        return self.results_votes(request, AssignmentPoll)

    def results_votes(self, request, model):
        poll, poll_id = self.get_request_object(request, model)
        vc = self.get_object()

        if vc.voting_mode != model.__name__ or vc.voting_target != poll_id:
            raise ValidationError({'detail': _('Another voting is active.')})

        if vc.voting_mode == 'MotionPoll':
            ballot = MotionBallot(poll, vc.principle)
        else:
            ballot = AssignmentBallot(poll)
        result = ballot.count_votes()

        return Response(result)

    @detail_route(['post'])
    def clear_motion_votes(self, request, **kwargs):
        """
        Clears all votes from a given motion poll: {poll_id: <poll_id>}.
        """
        return self.clear_votes(request, MotionPoll)

    @detail_route(['post'])
    def clear_assignment_votes(self, request, **kwargs):
        """
        Clears all votes from a given assignment poll: {poll_id: <poll_id>}.
        """
        return self.clear_votes(request, AssignmentPoll)

    def clear_votes(self, request, model):
        poll, _not_used = self.get_request_object(request, model)

        if poll.has_votes():
            poll.get_votes().delete()
            poll.votescast = poll.votesinvalid = poll.votesvalid = None
            poll.save()

        if model == MotionPoll:
            ballot = MotionBallot(poll)
        else:  # AssignmentPoll
            ballot = AssignmentBallot(poll)
        ballot.delete_ballots()

        vc = self.get_object()
        vc.votes_received = 0
        vc.save()

        return Response()

    @detail_route(['post'])
    def stop(self, request, **kwargs):
        """
        Stops a current voting/election
        """
        vc = self.get_object()

        # Remove voting prompt from projector.
        projector = Projector.objects.get(id=1)
        try:
            del projector.config[self.prompt_key]
        except KeyError:
            pass

        # Stop countdown and remove it from projector.
        if config['voting_auto_countdown']:
            try:
                countdown = Countdown.objects.get(pk=2)
            except Countdown.DoesNotExist:
                pass  # Do not create a new countdown on stop action
            else:
                countdown.control(action='stop')
                try:
                    del projector.config[self.countdown_key]
                except KeyError:
                    pass
        projector.save(information={'voting_prompt': True})

        # Attention: We purposely set is_voting to False even if stop_voting fails.
        vc.is_voting = False
        vc.save()

        AuthorizedVoters.clear_voting()

        self.force_stop_active_votecollector()

        return Response()

    def get_request_object(self, request, model, attr_name='poll_id'):
        obj_id = request.data.get(attr_name, None)
        if not isinstance(obj_id, int):
            raise ValidationError({'detail': _('The id has to be an int.')})
        try:
            obj = model.objects.get(pk=obj_id)
        except model.DoesNotExist:
            raise ValidationError({'detail': _('The object does not exist.')})
        return obj, obj_id


    @detail_route(['post'])
    def update_votecollector_device_status(self, request, **kwargs):
        """
        Queries the device status from the votecollector. Also updates the device_status
        field from the votingcontroller.
        """
        if not config['voting_enable_votecollector']:
            raise ValidationError({'detail': _('The VoteCollector is not enabled.')})

        vc = self.get_object()
        try:
            status = rpc.get_device_status()
        except rpc.VoteCollectorError as e:
            vc.device_status = e.value
            vc.save()
            return Response({'error': e.value})

        vc.device_status = status
        vc.save()
        return Response({
            'device': status,
            'connected': not status.startswith('Device: None')})

    @detail_route(['post'])
    def ping_votecollector(self,request, **kwargs):
        """
        Starts a ping to the votecollector.
        """
        if not config['voting_enable_votecollector']:
            raise ValidationError({'detail': _('The VoteCollector is not enabled.')})

        vc = self.get_object()
        self.force_stop_active_votecollector()
        url = rpc.get_callback_url(request) + '/keypad/'

        try:
            vc.votes_count, vc.device_status = rpc.start_voting('Ping', url)
        except rpc.VoteCollectorError as e:
            raise ValidationError({'detail': e.value})

        # Clear in_range and battery_level of all keypads.
        Keypad.objects.all().update(in_range=False, battery_level=-1)
        # We intentionally do not trigger an autoupdate.

        vc.voting_mode = 'ping'
        vc.voting_target = vc.votes_received = 0
        vc.is_voting = True
        vc.save()

        return Response()

    def force_stop_active_votecollector(self):
        if config['voting_enable_votecollector']:
            try:
                rpc.stop_voting()
            except rpc.VoteCollectorError as e:
                pass


class KeypadViewSet(PermissionMixin, ModelViewSet):
    access_permissions = KeypadAccessPermissions()
    queryset = Keypad.objects.all()


class VotingPrincipleViewSet(PermissionMixin, ModelViewSet):
    access_permissions = VotingPrincipleAccessPermissions()
    queryset = VotingPrinciple.objects.all()

    def validate_motions_and_assignments(self, request, exclude=None):
        # Check, if motions and assignments are not used by another VotingPrinciple.
        motions_id = request.data.get('motions_id', [])
        assignments_id = request.data.get('assignments_id', [])

        principles = VotingPrinciple.objects
        if exclude is not None:
            principles = principles.exclude(id=exclude.pk)

        for principle in principles.all():
            #from pdb import set_trace;set_trace();
            for motion_id in motions_id:
                if motion_id in principle.motions.values_list('pk', flat=True):
                    raise ValidationError({
                        'detail': 'Motion {} has already the principle {}!'.format(
                            Motion.objects.get(pk=motion_id).title,
                            principle.name)})
            for assignment_id in assignments_id:
                if assignment_id in principle.assignments.values_list('pk', flat=True):
                    raise ValidationError({
                        'detail': 'Election {} has already the principle {}!'.format(
                            Assignment.objects.get(pk=assignment_id).title,
                            principle.name)})

    def create(self, request, *args, **kwargs):
        self.validate_motions_and_assignments(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        own_principle = self.get_object()
        self.validate_motions_and_assignments(request, exclude=own_principle)
        return super().update(request, *args, **kwargs)


class VotingShareViewSet(PermissionMixin, ModelViewSet):
    access_permissions = VotingShareAccessPermissions()
    queryset = VotingShare.objects.all()


class VotingProxyViewSet(PermissionMixin, ModelViewSet):
    access_permissions = VotingProxyAccessPermissions()
    queryset = VotingProxy.objects.all()


class MotionAbsenteeVoteViewSet(PermissionMixin, ModelViewSet):
    access_permissions = MotionAbsenteeVoteAccessPermissions()
    queryset = MotionAbsenteeVote.objects.all()


class AssignmentAbsenteeVoteViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AssignmentAbsenteeVoteAccessPermissions()
    queryset = AssignmentAbsenteeVote.objects.all()


class MotionPollBallotViewSet(PermissionMixin, ModelViewSet):
    access_permissions = MotionPollBallotAccessPermissions()
    queryset = MotionPollBallot.objects.all()

    def get_poll(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'The data has to be a dict.'})
        poll_id = request.data.get('poll_id')
        if not isinstance(poll_id, int):
            raise ValidationError({'detail': 'The poll_id has to be an int.'})
        try:
            poll = MotionPoll.objects.get(pk=poll_id)
        except MotionPoll.DoesNotExist:
            raise ValidationError({'detail': 'The poll with id {} does not exist.'.format(
                poll_id)})
        return poll

    @list_route(methods=['post'])
    def recount_votes(self, request):
        """
        Recounts all votes from a given poll. Request data: {poll_id: <poll_id>}
        """
        poll = self.get_poll(request)

        # Count ballot votes.
        principle = VotingPrinciple.objects.filter(motions=poll.motion).first()
        ballot = MotionBallot(poll, principle)
        result = ballot.count_votes()

        # Update motion poll.
        votes = {
            'Yes': int(result['Y'][1]),
            'No': int(result['N'][1]),
            'Abstain': int(result['A'][1])
        }
        poll.set_vote_objects_with_values(poll.get_options().get(), votes, skip_autoupdate=True)
        poll.votescast = poll.votesvalid = int(result['casted'][1])
        poll.votesinvalid = 0
        poll.save()
        return HttpResponse()

    @list_route(methods=['post'])
    def pseudoanonymize_votes(self, request):
        """
        Pseudoanonymize all votes from a given poll. Request data: {poll_id: <poll_id>}
        """
        poll = self.get_poll(request)

        # Pseudoanonymize ballot votes.
        ballot = MotionBallot(poll)
        ballot.pseudo_anonymize_votes()
        return HttpResponse()


class BasePollTypeViewSet(ModelViewSet):
    """
    Base class for the PollTypeViewSets. Checks for permissions and validate
    the type on creation.
    """
    def check_view_permissions(self):
        """
        Just allow list and creation. Do not allow updates and deletes.
        """
        if self.action in ('list', 'retrieve', 'create'):
            return self.get_access_permissions().check_permissions(self.request.user)
        return False

    def create(self, request, *args, **kwargs):
        # check for a valid type option
        if not isinstance(request.data.get('type'), str):
            raise ValidationError({'detail': 'A type with type str has to be given.'})

        # get all defined choices from the config value:
        choices = config.config_variables['voting_default_voting_type'].choices
        if request.data.get('type') not in [c['value'] for c in choices]:
            raise ValidationError({'detail': 'The type is not valid.'})

        if request.data.get('type') == 'votecollector' and not config['voting_enable_votecollector']:
            raise ValidationError({'detail': 'The votecollector is not enabled.'})
        return super().create(request, *args, **kwargs)


class MotionPollTypeViewSet(BasePollTypeViewSet):
    access_permissions = MotionPollTypeAccessPermissions()
    queryset = MotionPollType.objects.all()


class AssignmentPollBallotViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AssignmentPollBallotAccessPermissions()
    queryset = AssignmentPollBallot.objects.all()


class AssignmentPollTypeViewSet(BasePollTypeViewSet):
    access_permissions = AssignmentPollTypeAccessPermissions()
    queryset = AssignmentPollType.objects.all()


class AttendanceLogViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AttendanceLogAccessPermissions()
    queryset = AttendanceLog.objects.all()

    @list_route(methods=['post'])
    def clear(cls, request):
        logs = AttendanceLog.objects.all()
        args = []
        for log in logs:
            args.append((log.get_collection_string(), log.pk))
        logs.delete()
        # Trigger autoupdate and setup response.
        if len(args) > 0:
            inform_deleted_data(args)
        return Response({'detail': 'All attendance logs deleted successfully.'})


class VotingTokenViewSet(ModelViewSet):
    access_permissions = VotingTokenAccessPermissions()
    queryset = VotingToken.objects.all()

    def check_view_permissions(self):
        """
        Just allow list, creation and generation. Do not allow updates and deletes.
        """
        if self.action in ('list', 'retrieve', 'create', 'generate'):
            return self.get_access_permissions().check_permissions(self.request.user)
        if self.action == 'check_token':
            # To prevent guessing and brute forcing valid tokens, just the voting machines are
            # allowed to check tokens
            return has_perm(self.request.user, 'openslides_voting.can_see_token_voting')
        return False

    @list_route(methods=['post'])
    def generate(self, request):
        """
        Generate n tokens. Provide N (1<=N<=4096) as the only argument: {N: <n>}
        """
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'The data has to be a dict.'})
        n = request.data.get('N')
        if not isinstance(n, int):
            raise ValidationError({'detail': 'N has to be an int.'})
        if n < 1 or n > 4096:
            raise ValidationError({'detail': 'N has to be between 1 and 4096.'})

        # no I,O,i,l,o,0
        choices = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrsuvwxyz123456789'
        tokens = [(''.join(random.choice(choices) for _ in range(12))) for _ in range(n)]
        return Response(tokens)

    @list_route(methods=['post'])
    def check_token(self, request):
        """
        Returns True or False, if the token is valid.
        The token has to be given as {token: <token>}.
        """
        # Check, if there is a token voting active.
        av = AuthorizedVoters.objects.get()
        if (not av.motion_poll and not av.assignment_poll) or av.type != 'token_based_electronic':
            raise ValidationError({'detail': 'No active token voting.'})
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'The request data has to be a dict'})
        token = request.data.get('token')
        if not isinstance(token, str):
            raise ValidationError({'detail': 'The token has to be a string'})
        if len(token) > 128:
            raise ValidationError({'detail': 'The token must be shorter then 128 characters'})

        token_valid = VotingToken.objects.filter(token=token).exists()

        return Response(token_valid)


@method_decorator(permission_required('openslides_voting.can_manage'), name='dispatch')
class AttendanceView(View):
    http_method_names = ['get']

    def get(self, request):
        total_shares = {
            'heads': [0, 0, 0, 0]  # [all, attending, in person, represented]
        }
        principle_ids = VotingPrinciple.objects.values_list('id', flat=True)
        for principle_id in principle_ids:
            total_shares[principle_id] = [Decimal(0), Decimal(0), Decimal(0), Decimal(0)]

        # Query delegates.
        delegates = User.objects.filter(groups=2).select_related('votingproxy', 'keypad').prefetch_related('shares')
        shares_exists = VotingShare.objects.exists()
        for delegate in delegates:
            # Exclude delegates without shares -- who may only serve as proxies.
            if shares_exists and delegate.shares.count() == 0:
                continue

            total_shares['heads'][0] += 1

            # Find the authorized voter.
            auth_voter, _not_used = find_authorized_voter(delegate)

            # If auth_voter is delegate himself set index to 2 (in person) else 3 (represented).
            i = 2 if auth_voter == delegate else 3
            attending = auth_voter is not None and auth_voter.is_present
            if config['voting_enable_votecollector']:
                attending = attending and hasattr(auth_voter, 'keypad')
            if attending:
                total_shares['heads'][i] += 1

            # Add shares to total.
            for share in delegate.shares.all():
                total_shares[share.principle_id][0] += share.shares
                if attending:
                    total_shares[share.principle_id][i] += share.shares

        for k in total_shares.keys():
            total_shares[k][1] = total_shares[k][2] + total_shares[k][3]

        # Add an attendance log entry if attendance has changed since last log.
        latest_head_count = -1
        if AttendanceLog.objects.exists():
            latest_head_count = AttendanceLog.objects.first().message['heads']
        if total_shares['heads'][1] != latest_head_count:
            message = {}
            for k, v in total_shares.items():
                message[str(k)] = float(v[1])
            log = AttendanceLog(message=message)
            log.save()

        return JsonResponse(total_shares)
