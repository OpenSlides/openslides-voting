import json

from django.apps import apps
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils.translation import ugettext as _

from openslides.agenda.models import Item, Speaker
from openslides.assignments.models import AssignmentOption, AssignmentPoll, AssignmentRelatedUser
from openslides.core.config import config
from openslides.core.exceptions import OpenSlidesError
from openslides.core.models import Countdown, Projector
from openslides.motions.models import MotionPoll
from openslides.utils import views as utils_views
from openslides.utils.autoupdate import inform_changed_data

from . import rpc
from ..models import Keypad, VotingController, MotionPollBallot, VotingShare
from ..voting import Ballot, get_admitted_delegates


class AjaxView(utils_views.View):
    """
    View for ajax requests.
    """
    required_permission = None

    def check_permission(self, request, *args, **kwargs):
        """
        Checks if the user has the required permission.
        """
        if self.required_permission is None:
            return True
        else:
            return request.user.has_perm(self.required_permission)

    def dispatch(self, request, *args, **kwargs):
        """
        Check if the user has the permission.

        If the user is not logged in, redirect the user to the login page.
        """
        if not self.check_permission(request, *args, **kwargs):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_ajax_context(self, **kwargs):
        """
        Returns a dictionary with the context for the ajax response.
        """
        return kwargs

    def ajax_get(self, request, *args, **kwargs):
        """
        Returns the HttpResponse.
        """
        return HttpResponse(json.dumps(self.get_ajax_context()))

    def get(self, request, *args, **kwargs):
        # TODO: Raise an error, if the request is not an ajax-request
        return self.ajax_get(request, *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.get(*args, **kwargs)


class VotingView(AjaxView):
    """
    Base view for the VotingController commands.
    """
    resource_path = '/votingcontroller'
    prompt_key = 'a016f7ecaf2147b2b656c6edf45c24ef'
    countdown_key = '134ddb26831743d586cbfa17e4712be9'

    vc = None
    result = None
    error = None

    def get_callback_url(self, request):
        host = request.META['SERVER_NAME']
        port = request.META.get('SERVER_PORT', 0)
        if port:
            return 'http://%s:%s%s' % (host, port, self.resource_path)
        else:
            return 'http://%s%s' % (host, self.resource_path)

    def get_poll_object(self):
        obj = None
        self.error = None
        app_label = self.kwargs.get('app')
        model_name = self.kwargs.get('model')
        model_id = self.kwargs.get('id')
        if app_label and model_name and model_id:
            model = apps.get_model(app_label, model_name)
            try:
                obj = model.objects.get(id=model_id)
            except model.DoesNotExist:
                self.error = _('Unknown id.')
        return obj

    def get_ajax_context(self, **kwargs):
        """
        Return the value of the called command, or the error-message
        """
        context = super().get_ajax_context(**kwargs)
        if self.error:
            context['error'] = self.error
        else:
            context.update(self.no_error_context())
        return context

    def no_error_context(self):
        """
        Return a dict for the template-context. Called if no errors occurred.
        """
        return {}

    @transaction.atomic
    def clear_votes(self, poll):
        # poll is MotionPoll or AssignmentPoll
        if poll.has_votes():
            poll.get_votes().delete()
            poll.votescast = poll.votesinvalid = poll.votesvalid = None
            poll.save()

        ballot = Ballot(poll)
        ballot.delete_ballots()

        self.vc = VotingController.objects.get()
        self.vc.votes_received = 0
        self.vc.save()


class DeviceStatus(VotingView):
    def get(self, request, *args, **kwargs):
        self.error = None
        try:
            self.result = rpc.get_device_status()
        except rpc.VoteCollectorError as e:
            self.error = e.value
        return super().get(request, *args, **kwargs)

    def no_error_context(self):
        return {
            'device': self.result,
            'connected': not self.result.startswith('Device: None')
        }


class StartVoting(VotingView):
    def get(self, request, *args, **kwargs):
        mode = kwargs['mode']
        resource = kwargs['resource']
        poll_obj = self.get_poll_object()
        self.vc = VotingController.objects.get()
        if not self.error:
            # Stop any active voting no matter what mode.
            if self.vc.is_voting:
                try:
                    rpc.stop_voting()
                except rpc.VoteCollectorError as e:
                    pass
            target = poll_obj.id if poll_obj else 0
            url = self.get_callback_url(request) + resource
            if target:
                url += '%s/' % target
            try:
                self.result, self.vc.device_status = rpc.start_voting(mode, kwargs.get('options'), url)
            except rpc.VoteCollectorError as e:
                self.error = e.value
            else:
                self.vc.voting_mode = kwargs.get('model', 'Test')
                self.vc.voting_target = target
                self.vc.voters_count = self.result
                self.vc.votes_received = 0
                self.vc.is_voting = True
                # Call on_start before saving vc to allow adjustments to vc.
                self.on_start(poll_obj)
                self.vc.save()
        return super().get(request, *args, **kwargs)

    def on_start(self, obj):
        pass

    def no_error_context(self):
        return {'count': self.result}


class StartYNA(StartVoting):
    def on_start(self, poll):
        # Limit voters count to length of admitted delegates list.
        delegates, self.vc.voters_count = get_admitted_delegates(poll.motion.category_id)
        if type(poll) == MotionPoll and Ballot:
            ballot = Ballot(poll)
            self.vc.votes_received = ballot.create_absentee_ballots()

        # Get candidate name (if is an election with one candidate only)
        candidate_str = ''
        if (type(poll) == AssignmentPoll) and (AssignmentOption.objects.filter(poll=poll).all().count() == 1):
            candidate = AssignmentOption.objects.filter(poll=poll)[0].candidate
            candidate_str = "<div class='spacer candidate'>" + str(candidate) + "</div>"

        # Show device dependent voting prompt on projector.
        yes = "<img src='/static/img/button-yes.png'> "
        no = "<img src='/static/img/button-no.png'> "
        abstain = "<img src='/static/img/button-abstain.png'> "
        if 'Interact' in self.vc.device_status:
            abstain = '2 = '
        elif 'Reply' in self.vc.device_status:
            yes = '1 = '
            no = '2 = '
            abstain = '3 = '
        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/prompt',
            'message':
                _(config['voting_start_prompt']) + " &nbsp;" +
                "<span class='nobr'>" + yes + _('Yes') + "</span> &nbsp;" +
                "<span class='nobr'>" + no + _('No') + "</span> &nbsp;" +
                "<span class='nobr'>" + abstain + _('Abstain') + "</span>" +
                candidate_str,
            'visible': True,
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


class StartElection(StartVoting):
    def on_start(self, poll):
        # Limit voters count to length of admitted delegates list.
        delegates, self.vc.voters_count = get_admitted_delegates(poll.motion.category_id)

        # Get candidate names (if is an election with >1 candidate)
        candidate_str = ''
        if (type(poll) == AssignmentPoll):
            options = AssignmentOption.objects.filter(poll=poll).order_by('weight').all()
            candidate_str += "<div><ul class='columns' data-columns='3'>"
            for index, option in enumerate(options):
                candidate_str += \
                        "<li><span class='key'>" + str(index + 1) + "</span> " + \
                        "<span class='candidate'>" + str(option.candidate) + "</span>"
            candidate_str += "<li><span class='key'>0</span> " + \
                        "<span class='candidate'>" + _('Abstain') +"</span>"
            candidate_str += "</ul></div>"

        # Show voting prompt on projector.
        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/prompt',
            'message': _(config['voting_start_prompt']) +
                "<br>" + candidate_str,
            'visible': True,
            'stable': True
        }
        projector.save(information={'voting_prompt': True})


class StartSpeakerList(StartVoting):
    def on_start(self, item):
        # Show voting icon on projector.
        projector = Projector.objects.get(id=1)
        projector.config[self.prompt_key] = {
            'name': 'voting/icon',
            'stable': True
        }
        projector.save(information={'voting_prompt': True})


class StartPing(StartVoting):
    def on_start(self, obj):
        # Clear in_range and battery_level of all keypads.
        Keypad.objects.all().update(in_range=False, battery_level=-1)
        # We intentionally do not trigger an autoupdate.


class StopVoting(VotingView):
    def get(self, request, *args, **kwargs):
        self.error = None

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

        try:
            self.result = rpc.stop_voting()
        except rpc.VoteCollectorError as e:
            self.error = e.value
        # Attention: We purposely set is_voting to False even if stop_voting fails.
        self.vc = VotingController.objects.get()
        self.vc.is_voting = False
        self.vc.save()
        return super().get(request, *args, **kwargs)


class ClearVotes(VotingView):
    def get(self, request, *args, **kwargs):
        poll = self.get_poll_object()
        if not self.error:
            self.clear_votes(poll)
        return super().get(request, *args, **kwargs)


class VotingStatus(VotingView):
    def get(self, request, *args, **kwargs):
        self.error = None
        try:
            self.result = rpc.get_voting_status()
        except rpc.VoteCollectorError as e:
            self.error = e.value
        return super().get(request, *args, **kwargs)

    def no_error_context(self):
        import time
        return {
            'elapsed': time.strftime('%M:%S', time.gmtime(self.result[0])),
            'votes_received': self.result[1]
        }


class VotingResult(VotingView):
    def get(self, request, *args, **kwargs):
        poll = self.get_poll_object()
        if not self.error:
            self.vc = VotingController.objects.get()
            if self.vc.voting_mode == kwargs['model'] and self.vc.voting_target == int(kwargs['id']):
                if self.vc.voting_mode == 'MotionPoll' and Ballot:
                    ballot = Ballot(poll)
                    result = ballot.count_votes()
                    self.result = [
                        int(result['Y'][1]),
                        int(result['N'][1]),
                        int(result['A'][1])
                    ]
                else:
                    # Get vote result from votecollector.
                    try:
                        self.result = rpc.get_voting_result()
                    except rpc.VoteCollectorError as e:
                        self.error = e.value
            else:
                self.error = _('Another voting is active.')
        return super().get(request, *args, **kwargs)

    def no_error_context(self):
        return {
            'votes': self.result
        }


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


class Votes(utils_views.View):
    http_method_names = ['post']

    @transaction.atomic()
    def post(self, request, poll_id):
        vc = VotingController.objects.get()

        # Get poll instance.
        poll_model = MotionPoll if vc.voting_mode == 'MotionPoll' else AssignmentPoll
        try:
            poll = poll_model.objects.get(id=poll_id)
        except poll_model.DoesNotExist:
            return HttpResponse()

        # Get ballot instance.
        ballot = Ballot(poll)

        # Load json list from request body.
        votes = json.loads(request.body.decode('utf-8'))
        keypad_set = set()
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
            value = vote['value']
            if value not in ('Y', 'N', 'A'):
                continue

            # Write ballot.
            # TODO: Implement assignment poll voting.
            if vc.voting_mode == 'MotionPoll':
                if ballot.register_vote(keypad_id, value, commit=True) > 0:
                    keypad_set.add(keypad.id)

        # Bulk create ballots and update votes received.
        vc.votes_received = ballot.save_ballots()
        vc.save()

        return HttpResponse()


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
            ballot = Ballot(poll)
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
