import os

from django.apps import AppConfig

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
        'static/js/openslides_voting/pdf.js',
        'static/js/openslides_voting/site.js',
        'static/js/openslides_voting/projector.js',
        'static/js/openslides_voting/templates.js'
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        import settings
        # Add the staticfiles dir to OpenSlides
        base_path = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
        # remove the app folder 'openslides_voting'
        base_path = os.path.dirname(base_path)
        settings.STATICFILES_DIRS.append(os.path.join(base_path, 'static'))

    def ready(self):
        # Load projector elements.
        # Do this by just importing all from these files.
        from . import projector

        # Import all required stuff.
        from openslides.core.config import config
        from openslides.core.signals import post_permission_creation
        from openslides.utils.rest_api import router
        from .config_variables import get_config_variables
        from .signals import add_permissions_to_builtin_groups
        from .urls import urlpatterns
        from .views import (
            AbsenteeVoteViewSet,
            AttendanceLogViewSet,
            KeypadViewSet,
            MotionPollBallotViewSet,
            VotingControllerViewSet,
            VotingShareViewSet,
            VotingPrincipleViewSet,
            VotingProxyViewSet
        )

        # Define config variables
        config.update_config_variables(get_config_variables())

        # Connect signals.
        post_permission_creation.connect(
            add_permissions_to_builtin_groups,
            dispatch_uid='voting_add_permissions_to_builtin_groups'
        )

        # Register viewsets.
        router.register(self.get_model('VotingController').get_collection_string(), VotingControllerViewSet)
        router.register(self.get_model('Keypad').get_collection_string(), KeypadViewSet)
        router.register(self.get_model('VotingPrinciple').get_collection_string(), VotingPrincipleViewSet)
        router.register(self.get_model('VotingShare').get_collection_string(), VotingShareViewSet)
        router.register(self.get_model('VotingProxy').get_collection_string(), VotingProxyViewSet)
        router.register(self.get_model('AbsenteeVote').get_collection_string(), AbsenteeVoteViewSet)
        router.register(self.get_model('AttendanceLog').get_collection_string(), AttendanceLogViewSet)
        router.register(self.get_model('MotionPollBallot').get_collection_string(), MotionPollBallotViewSet)

        # Provide plugin urlpatterns to application configuration.
        self.urlpatterns = urlpatterns

    def get_startup_elements(self):
        from openslides.utils.collection import Collection
        for model in ('VotingController', 'Keypad', 'VotingPrinciple', 'VotingShare',
                      'VotingProxy', 'AbsenteeVote', 'MotionPollBallot', 'AttendanceLog'):
            yield Collection(self.get_model(model).get_collection_string())
