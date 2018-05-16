from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from openslides.utils.access_permissions import BaseAccessPermissions as OSBaseAccessPermissions
from openslides.utils.auth import has_perm
from openslides.utils.collection import CollectionElement


def permission_required(perm, login_url=None, raise_exception=False):
    """
    Decorator for views that checks whether a user has a particular permission
    enabled, redirecting to the log-in page if necessary.
    If the raise_exception parameter is given the PermissionDenied exception
    is raised.
    """
    def check_perm(user):
        if has_perm(user, perm):
            return True
        if raise_exception:
            raise PermissionDenied
        return False
    return user_passes_test(check_perm, login_url=login_url)


class AuthorizedVotersAccessPermissions(OSBaseAccessPermissions):
    def check_permissions(self, user):
        """
        The user has to be logged in.
        """
        return user is not None and not isinstance(user, AnonymousUser)

    def get_serializer_class(self, user=None):
        from .serializers import AuthorizedVotersSerializer
        return AuthorizedVotersSerializer


class BaseAccessPermissions(OSBaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')


class VotingControllerAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import VotingControllerSerializer
        return VotingControllerSerializer


class KeypadAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import KeypadSerializer
        return KeypadSerializer


class VotingPrincipleAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import VotingPrincipleSerializer
        return VotingPrincipleSerializer


class VotingShareAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import VotingShareSerializer
        return VotingShareSerializer


class VotingProxyAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import VotingProxySerializer
        return VotingProxySerializer


class MotionAbsenteeVoteAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import MotionAbsenteeVoteSerializer
        return MotionAbsenteeVoteSerializer


class AssignmentAbsenteeVoteAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import AssignmentAbsenteeVoteSerializer
        return AssignmentAbsenteeVoteSerializer


class MotionPollBallotAccessPermissions(OSBaseAccessPermissions):
    def check_permissions(self, user):
        if user is None or isinstance(user, AnonymousUser):
            return False
        if has_perm(user, 'openslides_voting.can_manage'):
            return True

        # The user can see this, if he is listed there.
        from .models import MotionPollBallot
        return MotionPollBallot.objects.filter(delegate__pk=user.id).exists()

    def get_restricted_data(self, full_data, user):
        if not isinstance(user, CollectionElement):
            return []

        if has_perm(user, 'openslides_voting.can_manage'):
            return full_data

        for item in full_data:
            if item['delegate_id'] == user.id:
                return [item]
        return []

    def get_serializer_class(self, user=None):
        from .serializers import MotionPollBallotSerializer
        return MotionPollBallotSerializer


class MotionPollTypeAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import MotionPollTypeSerializer
        return MotionPollTypeSerializer


class AssignmentPollBallotAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        if user is None or isinstance(user, AnonymousUser):
            return False
        if has_perm(user, 'openslides_voting.can_manage'):
            return True

        # The user can see this, if he is listed there.
        from .models import AssignmentPollBallot
        return AssignmentPollBallot.objects.filter(delegate__pk=user.id).exists()

    def get_restricted_data(self, full_data, user):
        if not isinstance(user, CollectionElement):
            return []

        if has_perm(user, 'openslides_voting.can_manage'):
            return full_data

        for item in full_data:
            if item['delegate_id'] == user.id:
                return [item]
        return []

    def get_serializer_class(self, user=None):
        from .serializers import AssignmentPollBallotSerializer
        return AssignmentPollBallotSerializer


class AssignmentPollTypeAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import AssignmentPollTypeSerializer
        return AssignmentPollTypeSerializer


class AttendanceLogAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import AttendanceLogSerializer
        return AttendanceLogSerializer


class VotingTokenAccessPermissions(BaseAccessPermissions):
    def get_serializer_class(self, user=None):
        from .serializers import VotingTokenSerializer
        return VotingTokenSerializer
