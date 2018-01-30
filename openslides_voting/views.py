from decimal import Decimal

from django.db.models import Prefetch
from django.http.response import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View

from openslides.motions.models import Category, MotionPoll
from openslides.users.models import User
from openslides.utils.rest_api import ModelViewSet

from .access_permissions import (
    permission_required,
    AbsenteeVoteAccessPermissions,
    AttendanceLogAccessPermissions,
    KeypadAccessPermissions,
    MotionPollBallotAccessPermissions,
    VoteCollectorAccessPermissions,
    VotingProxyAccessPermissions,
    VotingShareAccessPermissions
)
from .models import AbsenteeVote, AttendanceLog, Keypad, MotionPollBallot, VoteCollector, VotingProxy, VotingShare
from .voting import Ballot, find_authorized_voter, get_admitted_delegates, is_registered


class VoteCollectorViewSet(ModelViewSet):
    access_permissions = VoteCollectorAccessPermissions()
    http_method_names = ['get', 'head', 'options']
    queryset = VoteCollector.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class KeypadViewSet(ModelViewSet):
    access_permissions = KeypadAccessPermissions()
    queryset = Keypad.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class VotingShareViewSet(ModelViewSet):
    access_permissions = VotingShareAccessPermissions()
    queryset = VotingShare.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class VotingProxyViewSet(ModelViewSet):
    access_permissions = VotingProxyAccessPermissions()
    queryset = VotingProxy.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class AbsenteeVoteViewSet(ModelViewSet):
    access_permissions = AbsenteeVoteAccessPermissions()
    queryset = AbsenteeVote.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class MotionPollBallotViewSet(ModelViewSet):
    access_permissions = MotionPollBallotAccessPermissions()
    queryset = MotionPollBallot.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class AttendanceLogViewSet(ModelViewSet):
    access_permissions = AttendanceLogAccessPermissions()
    queryset = AttendanceLog.objects.all()

    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


@method_decorator(permission_required('openslides_voting.can_manage'), name='dispatch')
class AttendanceView(View):
    http_method_names = ['get']

    def get(self, request):
        total_shares = {
            'heads': [0, 0, 0, 0]  # [all, attending, in person, represented]
        }
        cat_ids = Category.objects.values_list('id', flat=True)
        for cat_id in cat_ids:
            total_shares[cat_id] = [Decimal(0), Decimal(0), Decimal(0), Decimal(0)]

        # Query delegates.
        qs = User.objects.filter(groups=2).select_related('votingproxy', 'keypad').prefetch_related('shares')
        shares_exists = VotingShare.objects.exists()
        for delegate in qs:
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
            for vs in delegate.shares.all():
                total_shares[vs.category_id][0] += vs.shares
                if attending:
                    total_shares[vs.category_id][i] += vs.shares

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

    def get(self, request, cat_id=None):
        """
        Gets a JSON list of admitted delegates sorted by last_name, first_name, number.

        :param request:
        :param cat_id: category ID or None.
        :return: JSON list of delegate IDs.
        """
        delegates, count = get_admitted_delegates(cat_id, 'last_name', 'first_name', 'number')
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