import os

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from openslides.utils.projector import register_projector_elements

from . import (
    __description__,
    __license__,
    __url__,
    __verbose_name__,
    __version__,
)


class VotingAppConfig(AppConfig):
    name = 'openslides_voting'
    verbose_name = __verbose_name__
    description = __description__
    version = __version__
    license = __license__
    url = __url__
    angular_site_module = True
    angular_projector_module = True
    js_files = [
        'static/js/openslides_voting/base.js',
        'static/js/openslides_voting/templatehooks.js',
        'static/js/openslides_voting/site.js',
        'static/js/openslides_voting/pdf.js',
        'static/js/openslides_voting/projector.js',
        'static/js/openslides_voting/templates.js',
        'static/js/openslides_voting/libs.js'
    ]

    def ready(self):
        # Load projector elements.
        # Do this by just importing all from these files.
        from . import projector

        # Import all required stuff.
        from openslides.core.config import config
        from openslides.core.signals import post_permission_creation
        from openslides.users.models import Group, User
        from openslides.utils.rest_api import router
        from .config_variables import get_config_variables
        from .projector import get_projector_elements
        from .signals import (
            add_permissions_to_builtin_groups,
            update_authorized_voters,
            inform_keypad_deleted,
        )
        from .urls import urlpatterns
        from .models import Keypad, VotingShare
        from .views import (
            AssignmentAbsenteeVoteViewSet,
            AssignmentPollBallotViewSet,
            AssignmentPollTypeViewSet,
            AttendanceLogViewSet,
            AuthorizedVotersViewSet,
            KeypadViewSet,
            MotionAbsenteeVoteViewSet,
            MotionPollBallotViewSet,
            MotionPollTypeViewSet,
            VotingControllerViewSet,
            VotingPrincipleViewSet,
            VotingProxyViewSet,
            VotingShareViewSet,
            VotingTokenViewSet
        )

        # Register projector elements
        register_projector_elements(get_projector_elements())

        # Define config variables
        config.update_config_variables(get_config_variables())

        # Connect signals.
        post_permission_creation.connect(
            add_permissions_to_builtin_groups,
            dispatch_uid='voting_add_permissions_to_builtin_groups'
        )

        # TODO: Review if it's necessary or even desired to update authorized voters during voting.
        # post_save.connect(update_authorized_voters, sender=User)
        # post_save.connect(update_authorized_voters, sender=Group)
        # post_save.connect(update_authorized_voters, sender=VotingShare)
        # post_save.connect(update_authorized_voters, sender=Keypad)
        # post_delete.connect(update_authorized_voters, sender=VotingShare)
        # post_delete.connect(update_authorized_voters, sender=Keypad)
        post_delete.connect(inform_keypad_deleted, sender=Keypad)

        # Register viewsets.
        router.register(self.get_model('AssignmentAbsenteeVote').get_collection_string(), AssignmentAbsenteeVoteViewSet)
        router.register(self.get_model('AssignmentPollBallot').get_collection_string(), AssignmentPollBallotViewSet)
        router.register(self.get_model('AssignmentPollType').get_collection_string(), AssignmentPollTypeViewSet)
        router.register(self.get_model('AttendanceLog').get_collection_string(), AttendanceLogViewSet)
        router.register(self.get_model('AuthorizedVoters').get_collection_string(), AuthorizedVotersViewSet)
        router.register(self.get_model('Keypad').get_collection_string(), KeypadViewSet)
        router.register(self.get_model('MotionAbsenteeVote').get_collection_string(), MotionAbsenteeVoteViewSet)
        router.register(self.get_model('MotionPollBallot').get_collection_string(), MotionPollBallotViewSet)
        router.register(self.get_model('MotionPollType').get_collection_string(), MotionPollTypeViewSet)
        router.register(self.get_model('VotingToken').get_collection_string(), VotingTokenViewSet)
        router.register(self.get_model('VotingController').get_collection_string(), VotingControllerViewSet)
        router.register(self.get_model('VotingPrinciple').get_collection_string(), VotingPrincipleViewSet)
        router.register(self.get_model('VotingShare').get_collection_string(), VotingShareViewSet)
        router.register(self.get_model('VotingProxy').get_collection_string(), VotingProxyViewSet)

        # Provide plugin urlpatterns to application configuration.
        self.urlpatterns = urlpatterns

    def get_startup_elements(self):
        from openslides.utils.collection import Collection
        for model in ('AssignmentAbsenteeVote', 'AssignmentPollType', 'AssignmentPollBallot',
                'AttendanceLog', 'AuthorizedVoters', 'Keypad', 'MotionAbsenteeVote',
                'MotionPollType', 'MotionPollBallot', 'VotingToken', 'VotingController',
                'VotingShare', 'VotingPrinciple', 'VotingProxy'):
            yield Collection(self.get_model(model).get_collection_string())

    def get_angular_constants(self):
        # Custom settings
        voting_settings_dict = {
            'votingResultTokenTimeout': getattr(settings, 'VOTING_RESULT_TOKEN_TIMEOUT', 30),
        }
        voting_settings = {
            'name': 'VotingSettings',
            'value': voting_settings_dict,
        }

        # all polltypes
        from .models import POLLTYPES
        polltypes_dict = {}
        for polltype, verbose_name in POLLTYPES:
            polltypes_dict[polltype] = verbose_name
        polltypes = {
            'name': 'PollTypes',
            'value': polltypes_dict,
        }

        return [voting_settings, polltypes]
