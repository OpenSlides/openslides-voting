from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from openslides.users.models import Group


def add_permissions_to_builtin_groups(**kwargs):
    """
    Adds the permissions openslides_voting.can_manage to the group staff.
    """
    content_type = ContentType.objects.get(app_label='openslides_voting', model='votingcontroller')

    try:
        # Group with pk == 3 should be the staff group in OpenSlides 2.1
        staff = Group.objects.get(pk=3)
    except Group.DoesNotExist:
        pass
    else:
        perm_can_manage = Permission.objects.get(content_type=content_type, codename='can_manage')
        staff.permissions.add(perm_can_manage)
