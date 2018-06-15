from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from openslides.users.models import Group
from openslides.utils.autoupdate import inform_deleted_data

from .models import Keypad, AuthorizedVoters, VotingController
from .voting import get_admitted_delegates


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


def update_authorized_voters(sender, instance, **kwargs):
    vc = VotingController.objects.get()
    av = AuthorizedVoters.objects.get()

    if not vc.is_voting:
        return

    admitted_delegates = None
    if av.type == 'votecollector':
        vc.votes_count, admitted_delegates = get_admitted_delegates(vc.principle, keypad=True)
    elif av.type == 'named_electronic':
        vc.votes_count, admitted_delegates = get_admitted_delegates(vc.principle)

    if admitted_delegates:  # Something changed
        AuthorizedVoters.update_delegates(admitted_delegates)
        vc.save()


def inform_keypad_deleted(sender, instance, **kwargs):
    keypad = (Keypad.get_collection_string(), instance.pk)
    inform_deleted_data([keypad])
