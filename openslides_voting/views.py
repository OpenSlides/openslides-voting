import random

from decimal import Decimal

from django.db.models import Prefetch
from django.http.response import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View

from openslides.assignments.models import Assignment
from openslides.core.config import config
from openslides.motions.models import Category, Motion, MotionPoll
from openslides.users.models import User
from openslides.utils.autoupdate import inform_deleted_data
from openslides.utils.rest_api import ModelViewSet, ValidationError, list_route, Response

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
    http_method_names = ['get', 'head', 'options']
    queryset = VotingController.objects.all()


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
        delegates, count = get_admitted_delegates(principle_id, 'last_name', 'first_name', 'number')
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
