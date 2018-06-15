from openslides.core.exceptions import ProjectorException
from openslides.motions.models import MotionPoll
from openslides.users.models import User
from openslides.utils.projector import ProjectorElement

from .models import (
    AuthorizedVoters,
    AssignmentPollBallot,
    Keypad,
    MotionPollBallot,
    VotingController,
    VotingProxy,
    VotingShare,
)


class MotionPollSlide(ProjectorElement):
    """
    Slide definitions for Motion poll model.
    """
    name = 'voting/motion-poll'

    def check_data(self):
        if not MotionPoll.objects.filter(pk=self.config_entry.get('id')).exists():
            raise ProjectorException('MotionPoll does not exist.')

    def get_requirements(self, config_entry):
        try:
            motionpoll = MotionPoll.objects.get(pk=config_entry.get('id'))
        except MotionPoll.DoesNotExist:
            # MotionPoll does not exist. Just do nothing.
            pass
        else:
            yield motionpoll.motion
            yield motionpoll.motion.agenda_item
            # TODO: yield motionpoll.motion.category causes failure in function below
            yield AuthorizedVoters.objects.get()
            yield from User.objects.filter(groups=2)
            yield from Keypad.objects.all()
            yield from VotingProxy.objects.all()
            yield from VotingShare.objects.all()
            yield from MotionPollBallot.objects.filter(poll=motionpoll)
            yield VotingController.objects.get()

    def get_collection_elements_required_for_this(self, collection_element, config_entry):
        if collection_element.collection_string == MotionPollBallot.get_collection_string():
            output = [collection_element]
        elif collection_element.collection_string == VotingController.get_collection_string():
            output = [collection_element]
        elif collection_element.information.get('voting_prompt'):
            output = []
        else:
            output = super().get_collection_elements_required_for_this(collection_element, config_entry)
        return output


class AssignmentPollSlide(ProjectorElement):
    """
    Slide definitions for assignment poll model.
    """
    name = 'voting/assignment-poll'

    def check_data(self):
        if not AssignmentPoll.objects.filter(pk=self.config_entry.get('id')).exists():
            raise ProjectorException('AssignmentPoll does not exist.')

    def get_requirements(self, config_entry):
        try:
            assignmentpoll = AssignmentPoll.objects.get(pk=config_entry.get('id'))
        except AssignmentPoll.DoesNotExist:
            # AssignmentPoll does not exist. Just do nothing.
            pass
        else:
            yield assignmentpoll.assignment
            yield assignmentpoll.assignment.agenda_item
            # TODO: yield assignmentpoll.assignment.category causes failure in function below
            yield from User.objects.filter(groups=2)
            yield from Keypad.objects.all()
            yield from VotingProxy.objects.all()
            yield from VotingShare.objects.all()
            yield from AssignmentPollBallot.objects.filter(poll=assignmentpoll)
            yield VotingController.objects.get()

    def get_collection_elements_required_for_this(self, collection_element, config_entry):
        if collection_element.collection_string == AssignmentPollBallot.get_collection_string():
            output = [collection_element]
        elif collection_element.collection_string == VotingController.get_collection_string():
            output = [collection_element]
        elif collection_element.information.get('voting_prompt'):
            output = []
        else:
            output = super().get_collection_elements_required_for_this(collection_element, config_entry)
        return output


class VotingPrompt(ProjectorElement):
    """
    Voting prompt on the projector.
    """
    name = 'voting/prompt'

    def check_data(self):
        if self.config_entry.get('message') is None:
            raise ProjectorException('No message given.')


class VotingIcon(ProjectorElement):
    """
    Voting icon on the projector.
    """
    name = 'voting/icon'


def get_projector_elements():
    yield MotionPollSlide
    yield AssignmentPollSlide
    yield VotingPrompt
    yield VotingIcon
