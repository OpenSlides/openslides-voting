import json

from django.db import transaction
from django.http import HttpResponse
from django.utils.translation import ugettext as _

from openslides.agenda.models import Item, Speaker
from openslides.assignments.models import AssignmentOption, AssignmentPoll
from openslides.core.exceptions import OpenSlidesError
from openslides.motions.models import MotionPoll
from openslides.utils import views as utils_views
from openslides.utils.autoupdate import inform_changed_data

from . import rpc
from ..models import Keypad, VotingController, MotionPollBallot, VotingShare
from ..voting import Ballot


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
