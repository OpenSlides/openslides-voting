from django.core.management.base import LabelCommand

from openslides.users.models import User


class Command(LabelCommand):
    help = 'Make all users with keypad present.'

    def handle_label(self, label, **options):
        count = User.objects.exclude(keypad=None).update(is_present=label)
        print('Set is_present to %s on %d rows' % (label, count))
