from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from openslides.utils.access_permissions import BaseAccessPermissions
from openslides.utils.auth import has_perm


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


class VoteCollectorAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import VoteCollectorSerializer
        return VoteCollectorSerializer


class KeypadAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import KeypadSerializer
        return KeypadSerializer


class VotingShareAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import VotingShareSerializer
        return VotingShareSerializer


class VotingProxyAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import VotingProxySerializer
        return VotingProxySerializer


class AbsenteeVoteAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import AbsenteeVoteSerializer
        return AbsenteeVoteSerializer


class MotionPollBallotAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import MotionPollBallotSerializer
        return MotionPollBallotSerializer


class AttendanceLogAccessPermissions(BaseAccessPermissions):
    def check_permissions(self, user):
        return has_perm(user, 'openslides_voting.can_manage')

    def get_serializer_class(self, user=None):
        from .serializers import AttendanceLogSerializer
        return AttendanceLogSerializer
