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
from openslides.core.models import Projector
from openslides.motions.models import Category, Motion, MotionPoll
from openslides.users.models import User
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
    AbsenteeVoteAccessPermissions,
    AssignmentPollBallotAccessPermissions,
    AssignmentPollTypeAccessPermissions,
    AttendanceLogAccessPermissions,
    KeypadAccessPermissions,
    MotionPollBallotAccessPermissions,
    MotionPollTypeAccessPermissions,
    VotingControllerAccessPermissions,
    VotingProxyAccessPermissions,
    VotingPrincipleAccessPermissions,
    VotingShareAccessPermissions,
    VotingTokenAccessPermissions
)
from .models import (
    AbsenteeVote,
    AssignmentPollBallot,
    AssignmentPollType,
    AttendanceLog,
    Keypad,
    MotionPollBallot,
    MotionPollType,
    VotingController,
    VotingPrinciple,
    VotingProxy,
    VotingShare,
    VotingToken
)
from .voting import (
    Ballot,
    find_authorized_voter,
    get_admitted_delegates,
    is_registered
)


class PermissionMixin:
    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


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
        if self.action in ('list', 'retrieve', 'start_motion_yna', 'start_assignment_yna',
                'start_list_speakers', 'results_motion_votes', 'results_assignment_votes',
                'clear_motion_votes', 'clear_assignment_votes', 'stop',
                'update_votecollector_device_status', 'ping_votecollector'):
            return self.get_access_permissions().check_permissions(self.request.user)
        return False

    @detail_route(['post'])
    def start_motion_yna(self, request, **kwargs):
        """
        Starts a voting for a motion poll. The poll id has to be given as the only argument:
        {poll_id: <poll_id>}
        """
        return self.start_yna(request, MotionPoll)

    @detail_route(['post'])
    def start_assignment_yna(self, request, **kwargs):
        """
        Starts a yna electionfor an assignment poll. The poll id has to be
        given as the only argument: {poll_id: <poll_id>}
        """
        return self.start_yna(request, AssignmentPoll)

    def start_yna(self, request, model):
        vc = self.get_object()
        poll, poll_id = self.get_request_object(request, model)

        # get voting principle and type from motion or assignment
        principle = None
        voting_type = None
        if type(poll) == MotionPoll:
            try:
                principle = VotingPrinciple.objects.get(motions=poll.motion)
            except VotingPrinciple.DoesNotExist:
                pass

            try:
                voting_type = MotionPollType.objects.get(poll=poll).type
            except MotionPollType.DoesNotExist:
                pass

            vc.votes_received = Ballot(poll).create_absentee_ballots()

        # Get candidate name (if is an election with one candidate only)
        candidate_str = ''
        if type(poll) == AssignmentPoll:
            try:
                principle = VotingPrinciple.objects.get(assignments=poll.assignment)
            except VotingPrinciple.DoesNotExist:
                pass

            try:
                voting_type = AssignmentPollType.objects.get(poll=poll).type
            except AssignmentPollType.DoesNotExist:
                pass

            assignmentOptions = AssignmentOption.objects.filter(poll=poll)
            if assignmentOptions.count() == 1:
                candidate = assignmentOptions[0].candidate
                candidate_str = '<div class="spacer candidate">' + str(candidate) + '</div>'

        # Limit voters count to length of admitted delegates list.
        _not_used, vc.voters_count = get_admitted_delegates(principle)

        # If not given, use the default voting type
        if voting_type is None:
            voting_type = config['voting_default_voting_type']

        if voting_type == 'votecollector':
            if not config['voting_enable_votecollector']:
                raise ValidationError({'detail': 'The VoteCollector is not enabled'})

            # Stop any active voting no matter what mode.
            self.force_stop_active_votecollector()

            url = rpc.get_callback_url(request) + '/vote/'
            url += '%s/' % poll_id

            try:
                vc.voters_count, vc.device_status = rpc.start_voting('YesNoAbstain', url)
            except rpc.VoteCollectorError as e:
                raise ValidationError({'detail': e.value})
        else:
            # TODO: I think this is not right...
            vc.voters_count = User.objects.filter(groups__pk=2).count()

        vc.voting_mode = model.__name__
        vc.voting_target = poll_id
        vc.votes_received = 0
        vc.is_voting = True
        vc.save()

        # Show device dependent voting prompt on projector.
        yes = '<img src="/static/img/button-yes.png">'
        no = '<img src="/static/img/button-no.png">'
        abstain = '<img src="/static/img/button-abstain.png">'

        if voting_type == 'votecollector':
            if 'Interact' in vc.device_status:
                abstain = '2 = '
            elif 'Reply' in vc.device_status:
                yes = '1 = '
                no = '2 = '
                abstain = '3 = '

        message = _(config['voting_start_prompt']) + '&nbsp;' + \
            '<span class="nobr">' + yes + _('Yes') + '</span>&nbsp;' + \
            '<span class="nobr">' + no + _('No') + '</span>&nbsp;' + \
            '<span class="nobr">' + abstain + _('Abstain') + '</span>' + \
            candidate_str
        projector = self.add_voting_prompt(message, save=False)

        # Auto start countdown and add it to projector.
        if config['voting_auto_countdown']:
            self.start_auto_countdown()
        projector.save(information={'voting_prompt': True})

        return Response()

    @detail_route(['post'])
    def start_assignment(self, request, **kwargs):
        """
        Starts voting for an AssignmentPoll. Give the id by: {'poll_id': <poll_id>}
        """
        poll, poll_id = self.get_request_obejct(request, AssignmentPoll)
        vc = self.get_object()

        # get voting principle and type from motion or assignment
        principle = None
        voting_type = None

        try:
            principle = VotingPrinciple.objects.get(assignments=poll.assignment)
        except VotingPrinciple.DoesNotExist:
            pass

        try:
            voting_type = AssignmentPollType.objects.get(poll=poll).type
        except AssignmentPollType.DoesNotExist:
            pass

        # Get candidate name (if is an election with one candidate only)
        candidate_str = '<div><ul class="columns" data-columns="3">'
        options = AssignmentOption.objects.filter(poll=poll).order_by('weight').all()
        for index, option in enumerate(options):
            candidate_str += \
                    '<li><span class="key">' + str(index + 1) + '</span>' + \
                    '<span class="candidate">' + str(option.candidate) + '</span></li>'
        candidate_str += '<li><span class="key">0</span><span class="candidate">' + \
            _('Abstain') + '</span></li></ul></div>'

        # Limit voters count to length of admitted delegates list.
        _not_used, vc.voters_count = get_admitted_delegates(principle)

        # If not given, use the default voting type
        if voting_type is None:
            voting_type = config['voting_default_voting_type']

        if voting_type == 'votecollector':
            if not config['voting_enable_votecollector']:
                raise ValidationError({'detail': 'The VoteCollector is not enabled'})

            # Stop any active voting no matter what mode.
            self.force_stop_active_votecollector()

            url = rpc.get_callback_url(request) + '/candidate/'
            url += '%s/' % poll_id

            try:
                vc.voters_count, vc.device_status = rpc.start_voting('SingleDigit', url)
            except rpc.VoteCollectorError as e:
                raise ValidationError({'detail': e.value})
        else:
            # TODO: I think this is not right...
            vc.voters_count = User.objects.filter(groups__pk=2).count()

        vc.voting_mode = 'AssignmentPoll'
        vc.voting_target = poll_id
        vc.votes_received = 0
        vc.is_voting = True
        vc.save()

        message = _(config['voting_start_prompt']) + '<br>' + candidate_str
        self.add_voting_prompt(message)

    def add_voting_prompt(self, message, save=True):
        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/prompt',
            'message': message,
            'visible': True,
            'stable': True
        }
        if save:
            projector.save(information={'voting_prompt': True})
        return projector

    def start_auto_countdown(self):
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
            vc.voters_count, self.vc.device_status = rpc.start_voting('SpeakerList', url)
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
            ballot = Ballot(poll)
            votes = ballot.count_votes()
            result = [
                int(votes['Y'][1]),
                int(votes['N'][1]),
                int(votes['A'][1])
            ]
        else:
            raise NotImplementedError('TODO in views.VotingControllerViewSet.results_votes')
        # TODO: This does not seem to be correct. What does the mode has to do with
        # the votecollector??

        #else:
        #    # Get vote result from votecollector.
        #    try:
        #        self.result = rpc.get_voting_result()
        #    except rpc.VoteCollectorError as e:
        #        self.error = e.value
        return Response({'votes': result})

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

        # TODO
        if model == MotionPoll:
            ballot = Ballot(poll)
            ballot.delete_ballots()
        else:  # AssignmentPoll
            raise NotImplementedError('TODO in views.VotingControllerViewSet.clear_votes')

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
            raise ValidationError({'detail': _('The VoteColelctor is not enabled.')})

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
            vc.voters_count, vc.device_status = rpc.start_voting('Ping', url)
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


class AbsenteeVoteViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AbsenteeVoteAccessPermissions()
    queryset = AbsenteeVote.objects.all()


class MotionPollBallotViewSet(PermissionMixin, ModelViewSet):
    access_permissions = MotionPollBallotAccessPermissions()
    queryset = MotionPollBallot.objects.all()


class MotionPollTypeViewSet(ModelViewSet):
    access_permissions = MotionPollTypeAccessPermissions()
    queryset = MotionPollType.objects.all()

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


class AssignmentPollBallotViewSet(PermissionMixin, ModelViewSet):
    access_permissions = AssignmentPollBallotAccessPermissions()
    queryset = AssignmentPollBallot.objects.all()


class AssignmentPollTypeViewSet(ModelViewSet):
    access_permissions = AssignmentPollTypeAccessPermissions()
    queryset = AssignmentPollType.objects.all()

    def check_view_permissions(self):
        """
        Just allow list and creation. Do not allow updates and deletes.
        """
        if self.action in ('list', 'retrieve', 'create'):
            return self.get_access_permissions().check_permissions(self.request.user)
        return False

    def create(self, request, *args, **kwargs):
        # TODO: check for a valid type option
        return super().create(request, *args, **kwargs)


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
        print(self.action)
        if self.action in ('list', 'retrieve', 'create', 'generate'):
            return self.get_access_permissions().check_permissions(self.request.user)
        return False

    @list_route(methods=['post'])
    def generate(self, request):
        """
        Generate n tokens. Provide N (1<=N<=4096) as the only argument: {N: <n>}
        """
        n = request.data.get('N')
        if not isinstance(n, int):
            raise ValidationError({'detail': 'N has to be an int.'})
        if n < 1 or n > 4096:
            raise ValidationError({'detail': 'N has to be between 1 and 4096.'})

        # no I,O,i,l,o,0
        choices = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrsuvwxyz123456789'
        tokens = [(''.join(random.choice(choices) for _ in range(12))) for _ in range(n)]
        return Response(tokens)


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
            auth_voter = find_authorized_voter(delegate)

            # If auth_voter is delegate himself set index to 2 (in person) else 3 (represented).
            i = 2 if auth_voter == delegate else 3
            attending = is_registered(auth_voter)
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


@method_decorator(permission_required('openslides_voting.can_manage'), name='dispatch')
class AdmittedDelegatesView(View):
    http_method_names = ['get']

    def get(self, request, principle_id=None):
        """
        Gets a JSON list of admitted delegates sorted by last_name, first_name, number.

        :param request:
        :param principle_id: Principle ID or None.
        :return: JSON list of delegate IDs.
        """
        try:
            principle = VotingPrinciple.objects.get(pk=principle_id)
        except VotingPrinciple.DoesNotExist:
            principle = None
        delegates, count = get_admitted_delegates(principle, 'last_name', 'first_name', 'number')
        admitted = {'delegates': delegates}
        return JsonResponse(admitted)


@method_decorator(permission_required('openslides_voting.can_manage'), name='dispatch')
class CountVotesView(View):
    http_method_names = ['post']

    def post(self, request, poll_id):
        poll = get_object_or_404(MotionPoll, id=poll_id)

        # Count ballot votes.
        ballot = Ballot(poll)
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
