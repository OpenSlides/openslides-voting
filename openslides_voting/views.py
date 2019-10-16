import random

from decimal import Decimal

from django.db import transaction
from django.http.response import HttpResponse, JsonResponse
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
from openslides.utils.autoupdate import inform_changed_data, inform_deleted_data
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
    get_total_shares,
)


class PermissionMixin:
    def check_view_permissions(self):
        return self.get_access_permissions().check_permissions(self.request.user)


class VoteCollectorPermissionMixin:
    """
    This mixin checks if the votecollector is enabled.
    """
    def check_view_permissions(self):
        if not config['voting_enable_votecollector']:
            raise ValidationError({'detail': 'The votecollector is not enabled.'})
        return self.get_access_permissions().check_permissions(self.request.user)


class ProxiesPermissionMixin:
    """
    This mixin checks if proxy voting is enabled.
    """
    def check_view_permissions(self):
        if not config['voting_enable_proxies']:
            raise ValidationError({'detail': 'Proxy voting is not enabled.'})
        return self.get_access_permissions().check_permissions(self.request.user)


class PrinciplesPermissionMixin:
    """
    This mixin checks if voting principles and shares are enabled.
    """
    def check_view_permissions(self):
        if not config['voting_enable_principles']:
            raise ValidationError({'detail': 'Voting principles and shares are not enabled.'})
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
        The one and only voting controller is created during migrations.
        """
        if self.action in ('list', 'retrieve', 'start_motion', 'start_assignment',
                'start_speaker_list', 'results_motion_votes', 'results_assignment_votes',
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
        projector_yes = '<button type="button" class="btn btn-default btn-voting-sm btn-yes"> \
            <i class="fa fa-thumbs-o-up fa-2x"></i></button>'
        projector_no = '<button type="button" class="btn btn-default btn-voting-sm btn-no"> \
            <i class="fa fa-thumbs-o-down fa-2x"></i></button>'
        projector_abstain = '<button type="button" class="btn btn-default btn-voting-sm btn-abstain"> \
            <i class="fa fa-circle-o fa-2x"></i></button>'
        if type(poll) == MotionPoll:
            projector_message = _(config['voting_start_prompt_motions'])
            principle = VotingPrinciple.get(motion=poll.motion)

            try:
                voting_type = MotionPollType.objects.get(poll=poll).type
            except MotionPollType.DoesNotExist:
                voting_type = config['voting_default_voting_type']

            if voting_type.startswith('votecollector'):
                if 'Interact' in vc.device_status:
                    projector_yes = "<img src='/static/img/button-interact-yes.png'> "
                    projector_no = "<img src='/static/img/button-interact-no.png'> "
                    projector_abstain = "<img src='/static/img/button-interact-abstain.png'> "
                elif 'Reply' in vc.device_status:
                    projector_yes = '1 = '
                    projector_no = '2 = '
                    projector_abstain = '3 = '
                projector_message += '<br>' + \
                '<span class="nobr">' + projector_yes + _('Yes') + '</span>&nbsp;' + \
                '<span class="nobr spacer-left">' + projector_no + _('No') + '</span>&nbsp;' + \
                '<span class="nobr spacer-left">' + projector_abstain + _('Abstain') + '</span>'

            votecollector_mode = 'YesNoAbstain'
            votecollector_options = None
            votecollector_resource = '/vote/'

            ballot = MotionBallot(poll, principle)
        elif type(poll) == AssignmentPoll:
            projector_message = _(config['voting_start_prompt_assignments'])
            principle = VotingPrinciple.get(assignment=poll.assignment)

            try:
                voting_type = AssignmentPollType.objects.get(poll=poll).type
            except AssignmentPollType.DoesNotExist:
                voting_type = config['voting_default_voting_type']

            options = AssignmentOption.objects.filter(poll=poll).order_by('weight')
            # check, if the pollmethod is supported by the votecollector
            # If so, calculate the projector message for the voting prompt
            if voting_type.startswith('votecollector'):
                if poll.pollmethod == 'yn' or (poll.pollmethod == 'yna' and options.count() is not 1):
                    raise ValidationError({'detail':
                        'The votecollector does not support the pollmethod {} (with {} candidates).'.format(
                            poll.pollmethod,
                            options.count())})

                if 'Interact' in vc.device_status:
                    projector_yes = "<img src='/static/img/button-interact-yes.png'> "
                    projector_no = "<img src='/static/img/button-interact-no.png'> "
                    projector_abstain = "<img src='/static/img/button-interact-abstain.png'> "
                elif 'Reply' in vc.device_status:
                    projector_yes = '1 = '
                    projector_no = '2 = '
                    projector_abstain = '3 = '

                # calculate the candidate string
                if poll.pollmethod == 'yna':
                    candidate = str(options.all()[0].candidate)
                    projector_message += '<br>' + \
                        '<span class="nobr">' + projector_yes + _('Yes') + '</span>&nbsp;' + \
                        '<span class="nobr">' + projector_no + _('No') + '</span>&nbsp;' + \
                        '<span class="nobr">' + projector_abstain + _('Abstain') + '</span>' + \
                        '<div class="spacer candidate">' + candidate + '</div>'

                    votecollector_mode = 'YesNoAbstain'
                    votecollector_options = None
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
                        votecollector_options = '10'  # unlock all keys 0 to 9
                    else:
                        votecollector_mode = 'MultiDigit'
                        votecollector_options = '2'  # limit votes to 2 digits, only applies to simulator
                    votecollector_resource = '/candidate/'

            ballot = AssignmentBallot(poll)
        else:
            raise ValidationError({'detail': 'Not supported type {}.'.format(type(poll))})

        # Delete all old votes and create absentee ballots
        ballot.delete_ballots()
        absentee_ballots_created = 0
        if config['voting_enable_proxies']:
            absentee_ballots_created = ballot.create_absentee_ballots()

        if voting_type.startswith('votecollector'):
            if not config['voting_enable_votecollector']:
                raise ValidationError({'detail': 'The VoteCollector is not enabled'})

            # Stop any active voting no matter what mode.
            self.force_stop_active_votecollector()

            url = rpc.get_callback_url(request) + votecollector_resource
            url += '%s/' % poll_id

            try:
                vc.votes_count, vc.device_status = rpc.start_voting(votecollector_mode, url, votecollector_options)
            except rpc.VoteCollectorError as e:
                raise ValidationError({'detail': e.value})

            # Limit voters count to length of admitted delegates list.
            admitted_count, admitted_delegates = get_admitted_delegates(principle, keypad=True)
            if not voting_type == 'votecollector_anonymous':
                vc.votes_count = admitted_count

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
        # search projector with an projected "related item". This item might be the motion/assignment
        # itself or the voting/(motion/assignment)-poll slide. If none was found, use the default projector

        if type(poll) == MotionPoll:
            objectElementName = 'motions/motion'
            objectElementId = poll.motion.id
            pollElementName = 'voting/motion-poll'
        else:
            objectElementName = 'assignments/assignment'
            objectElementId = poll.assignment.id
            pollElementName = 'voting/assignment-poll'

        projector = None
        found_projector = False
        for p in Projector.objects.all():
            if found_projector:
                break
            for uuid, element in p.elements.items():
                if found_projector:
                    break
                if element['name'] == objectElementName and element['id'] == objectElementId:
                    projector = p
                    found_projector = True
                if element['name'] == pollElementName and element['id'] == poll_id:
                    projector = p
                    found_projector = True
        if not found_projector:
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
        Starts a voting for the speakers list. The item id has to be given as the only argument:
        {item_id: <item_id>}
        """
        # Requires the votecollector.
        if not config['voting_enable_votecollector']:
            raise ValidationError({'detail': 'The VoteCollector is not enabled'})

        vc = self.get_object()
        item, item_id = self.get_request_object(request, Item, attr_name='item_id')

        # Stop any active voting no matter what mode.
        self.force_stop_active_votecollector()

        url = rpc.get_callback_url(request) + '/speaker/' + str(item_id) + '/'

        try:
            vc.votes_count, vc.device_status = rpc.start_voting('SpeakerList', url)
        except rpc.VoteCollectorError as e:
            raise ValidationError({'detail': e.value})

        vc.voting_mode = 'Item'
        vc.voting_target = item_id
        vc.votes_received = 0
        vc.is_voting = True
        vc.principle = None
        vc.save()

        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/icon',
            'stable': True
        }
        projector.save(information={'voting_prompt': True})

        return Response()

    @detail_route(['post'])
    def results_motion_votes(self, request, **kwargs):
        """
        Get results from a motion poll: {poll_id: <poll_id>}.
        """
        return self.results_votes(request, MotionPoll, MotionBallot, 'motionpolltype')

    @detail_route(['post'])
    def results_assignment_votes(self, request, **kwargs):
        """
        Get results from a given assignment poll: {poll_id: <poll_id>}.
        """
        return self.results_votes(request, AssignmentPoll, AssignmentBallot, 'assignmentpolltype')

    def results_votes(self, request, poll_model, ballot_model, poll_type_str):
        poll, poll_id = self.get_request_object(request, poll_model)
        vc = self.get_object()

        if vc.voting_mode != poll_model.__name__ or vc.voting_target != poll_id:
            raise ValidationError({'detail': _('Another voting is active.')})

        # Count the votes of the ballot.
        ballot = ballot_model(poll, vc.principle)
        result = ballot.count_votes()

        # Destroy the ballots for secret voting types.
        voting_type = getattr(poll, poll_type_str).type
        if voting_type in ('votecollector_secret', 'votecollector_pseudo_secret'):
            ballot.delete_ballots()

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
            if model == AssignmentPoll:
                poll.votesabstain = poll.votesno = None
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

        # Remove voting prompt from all projectors.
        for projector in Projector.objects.all():
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

        if config['voting_enable_votecollector']:
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
        Gets the device status from the votecollector. Updates the device_status
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
            raise ValidationError({'detail': e.value})

        # Typical status messages: 'Device: None. Status: Disconnected', 'Device: Simulator. Status: Connected'
        vc.device_status = status
        vc.save()
        return Response({
            'device': status,
            'connected': ' connected' in status.lower()
        })

    @detail_route(['post'])
    def ping_votecollector(self,request, **kwargs):
        """
        Starts pinging votecollector keypads.
        """
        if not config['voting_enable_votecollector']:
            raise ValidationError({'detail': _('The VoteCollector is not enabled.')})

        vc = self.get_object()

        # Stop any active voting no matter what mode.
        self.force_stop_active_votecollector()
        url = rpc.get_callback_url(request) + '/keypad/'

        try:
            vc.votes_count, vc.device_status = rpc.start_voting('Ping', url)
        except rpc.VoteCollectorError as e:
            raise ValidationError({'detail': e.value})

        # Clear in_range and battery_level of all keypads.
        # We intentionally do not trigger an autoupdate.
        Keypad.objects.all().update(in_range=False, battery_level=-1)

        vc.voting_mode = 'ping'
        vc.voting_target = vc.votes_received = 0
        vc.is_voting = True
        vc.voting_principle = None
        vc.save()

        return Response()

    def force_stop_active_votecollector(self):
        """
        Stops any orphaned votecollector voting.
        """
        if config['voting_enable_votecollector']:
            try:
                rpc.stop_voting()
            except rpc.VoteCollectorError:
                pass


class KeypadViewSet(VoteCollectorPermissionMixin, ModelViewSet):
    access_permissions = KeypadAccessPermissions()
    queryset = Keypad.objects.all()


class VotingPrincipleViewSet(PrinciplesPermissionMixin, ModelViewSet):
    access_permissions = VotingPrincipleAccessPermissions()
    queryset = VotingPrinciple.objects.all()

    def check_view_permissions(self):
        """
        Returns True if the user has required permissions.
        """
        if self.action in ('list', 'retrieve'):
            result = True
        else:
            result = has_perm(self.request.user, 'openslides_voting.can_manage')
        return result

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


class VotingShareViewSet(PrinciplesPermissionMixin, ModelViewSet):
    access_permissions = VotingShareAccessPermissions()
    queryset = VotingShare.objects.all()

    @list_route(methods=['post'])
    @transaction.atomic
    def mass_import(self, request):
        """
        Imports a list of VotingShare objects.

        Updates existing objects and creates new ones. Deletes existing objects if shares are zero.

        Clients are not being updated to avoid worker being overloaded. Clients need to refresh the store:
        >> VotingShare.ejectAll();
        >> VotingShare.findAll();
        :return: Number of delegates with voting shares
        """
        data = request.data.get('shares')
        if not isinstance(data, list):
            raise ValidationError({'detail': _('Shares has to be a list.')})

        created_shares = []
        deleted = []
        for d in data:
            vs = VotingShare(**d)
            try:
                # Look for an existing object and update its shares.
                existing = VotingShare.objects.get(delegate_id=vs.delegate_id, principle_id=vs.principle_id)
                if vs.shares == 0:
                    deleted.append(existing.id)
                elif vs.shares != float(existing.shares):
                    vs.id = existing.id
                    vs.save(skip_autoupdate=True)
            except VotingShare.DoesNotExist:
                # Append the data object for bulk create.
                if vs.shares > 0:
                    created_shares.append(vs)

        # Delete shares.
        del_shares = VotingShare.objects.filter(id__in=deleted)
        del_shares.delete()

        # Bulk create new shares.
        VotingShare.objects.bulk_create(created_shares)

        # FIXME: Delete cache keys so clients will get fresh data from db wit VotingShare.findAll().
        # from django.core import cache
        # cache.delete_pattern('*voting-share*')  # This works only for redis.
        # cache.delete()

        # Return number of delegates with shares.
        return Response({'count': User.objects.exclude(shares=None).count()})


class VotingProxyViewSet(ProxiesPermissionMixin, ModelViewSet):
    access_permissions = VotingProxyAccessPermissions()
    queryset = VotingProxy.objects.all()


class MotionAbsenteeVoteViewSet(ProxiesPermissionMixin, ModelViewSet):
    access_permissions = MotionAbsenteeVoteAccessPermissions()
    queryset = MotionAbsenteeVote.objects.all()


class AssignmentAbsenteeVoteViewSet(ProxiesPermissionMixin, ModelViewSet):
    access_permissions = AssignmentAbsenteeVoteAccessPermissions()
    queryset = AssignmentAbsenteeVote.objects.all()


class BasePollBallotViewSet(PermissionMixin, ModelViewSet):
    def get_poll(self, request, model):
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'Data must be a dictionary.'})
        poll_id = request.data.get('poll_id')
        if not isinstance(poll_id, int):
            raise ValidationError({'detail': 'poll_id must be an integer.'})
        try:
            poll = model.objects.get(pk=poll_id)
        except model.DoesNotExist:
            raise ValidationError({'detail': 'The poll with id {} does not exist.'.format(
                poll_id)})
        return poll


class MotionPollBallotViewSet(BasePollBallotViewSet):
    access_permissions = MotionPollBallotAccessPermissions()
    queryset = MotionPollBallot.objects.all()

    @list_route(methods=['post'])
    def recount_votes(self, request):
        """
        Recounts all votes for a given poll.
        :param request: Data: {poll_id: <poll_id>}
        """
        poll = self.get_poll(request, MotionPoll)

        # Count ballot votes.
        principle = VotingPrinciple.get(motion=poll.motion)
        ballot = MotionBallot(poll, principle)
        result = ballot.count_votes()

        # Update motion poll.
        votes = {
            'Yes': result['Y'][1],
            'No': result['N'][1],
            'Abstain': result['A'][1]
        }
        poll.set_vote_objects_with_values(poll.get_options().get(), votes, skip_autoupdate=True)
        poll.votescast = result['casted'][1]
        poll.votesvalid = result['valid'][1]
        poll.votesinvalid = result['invalid'][1]
        poll.save()
        return HttpResponse()

    @list_route(methods=['post'])
    def pseudo_anonymize_votes(self, request):
        """
        Pseudo anonymize all votes for a given poll.
        """
        MotionBallot(self.get_poll(request, MotionPoll)).pseudo_anonymize_votes()
        return HttpResponse()


class AssignmentPollBallotViewSet(BasePollBallotViewSet):
    access_permissions = AssignmentPollBallotAccessPermissions()
    queryset = AssignmentPollBallot.objects.all()

    @list_route(methods=['post'])
    def recount_votes(self, request):
        """
        Recounts all votes for a given poll.
        :param request: Data: {poll_id: <poll_id>}
        """
        poll = self.get_poll(request, AssignmentPoll)

        # Count ballot votes.
        principle = VotingPrinciple.get(assignment=poll.assignment)
        ballot = AssignmentBallot(poll, principle)
        result = ballot.count_votes()

        # Update assignment poll.
        if poll.pollmethod in ('yn', 'yna'):
            for option in poll.get_options():
                cid = str(option.candidate_id)
                votes = {
                    'Yes': result[cid]['Y'][1],
                    'No': result[cid]['N'][1]
                }
                if poll.pollmethod == 'yna':
                    votes['Abstain'] = result[cid]['A'][1]
                poll.set_vote_objects_with_values(option, votes, skip_autoupdate=True)
        else:  # votes
            for option in poll.get_options():
                cid = str(option.candidate_id)
                votes = {'Votes': result[cid][1]}
                poll.set_vote_objects_with_values(option, votes, skip_autoupdate=True)
        poll.votescast = result['casted'][1]
        poll.votesvalid = result['valid'][1]
        poll.votesinvalid = result['invalid'][1]
        poll.save()
        return HttpResponse()

    @list_route(methods=['post'])
    def pseudo_anonymize_votes(self, request):
        """
        Pseudo anonymize all votes for a given poll.
        """
        AssignmentBallot(self.get_poll(request, AssignmentPoll)).pseudo_anonymize_votes()
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


class AssignmentPollTypeViewSet(BasePollTypeViewSet):
    access_permissions = AssignmentPollTypeAccessPermissions()
    queryset = AssignmentPollType.objects.all()


class AttendanceLogViewSet(VoteCollectorPermissionMixin, ModelViewSet):
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

    def create(self, request, *args, **kwargs):
        try:
            token = request.data['token']
        except KeyError:
            raise ValidationError({'detail': 'You have to provide a token.'})
        if not isinstance(token, str):
            raise ValidationError({'detail': 'The token must be a string.'})
        if len(token) < 10:
            raise ValidationError({'detail': 'The token has to have at least 10 characters.'})

        return super().create(request, *args, **kwargs)

    @list_route(methods=['post'])
    def generate(self, request):
        """
        Generate n tokens. Provide N (1<=N<=4096) for the amount and enable_tokens
        to enable all generated tokens. Request data:
        {N: <n>, enable_tokens: Optional<boolean>}
        """
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'The data has to be a dict.'})
        n = request.data.get('N')
        if not isinstance(n, int):
            raise ValidationError({'detail': 'N has to be an int.'})
        if n < 1 or n > 4096:
            raise ValidationError({'detail': 'N has to be between 1 and 4096.'})
        enable_tokens = bool(request.data.get("enable_tokens"))

        # no I,O,i,l,o,0
        choices = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrsuvwxyz123456789'
        tokens = [(''.join(random.choice(choices) for _ in range(12))) for _ in range(n)]

        if enable_tokens:
            existing_token_ids = list(VotingToken.objects.values_list('id', flat=True))  # Evaluate queryset now.
            VotingToken.objects.bulk_create([
                VotingToken(token=token) for token in tokens
            ])
            inform_changed_data(VotingToken.objects.exclude(id__in=existing_token_ids))

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
        if not config['voting_enable_votecollector']:
            return JsonResponse({'detail': _('The votecollector is not active')})

        total_shares = get_total_shares()

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
