from django.utils.translation import ugettext_noop

from openslides.core.config import ConfigVariable
from .models import POLLTYPES


def get_config_variables():
    """
    Generator which yields all config variables of this app.
    It has to be evaluated during app loading (see apps.py).
    """
    # General
    yield ConfigVariable(
        name='voting_enable_votecollector',
        default_value=False,
        input_type='boolean',
        label='Enable VoteCollector',
        weight=615,
        group='OpenSlides-Voting',
        subgroup='General'
    )
    yield ConfigVariable(
        name='voting_enable_proxies',
        default_value=False,
        input_type='boolean',
        label='Enable proxies and absentee votes',
        weight=616,
        group='OpenSlides-Voting',
        subgroup='General'
    )
    yield ConfigVariable(
        name='voting_enable_principles',
        default_value=False,
        input_type='boolean',
        label='Enable shares and principles',
        weight=617,
        group='OpenSlides-Voting',
        subgroup='General'
    )
    choices = [{'value': c[0], 'display_name': c[1]} for c in POLLTYPES]
    yield ConfigVariable(
        name='voting_default_voting_type',
        default_value='analog',
        input_type='choice',
        label='Default voting type',
        choices=choices,
        weight=620,
        group='OpenSlides-Voting',
        subgroup='General'
    )
    yield ConfigVariable(
        name='voting_auto_countdown',
        default_value=False,
        input_type='boolean',
        label='Use countdown timer',
        help_text='Auto-start and stop a countdown timer when voting starts and stops.',
        weight=630,
        group='OpenSlides-Voting',
        subgroup='General'
    )

    # VoteCollector
    yield ConfigVariable(
        # TODO: Use URL validator.
        name='voting_votecollector_uri',
        default_value='http://localhost:8030',
        label='VoteCollector URL',
        help_text='Example: http://localhost:8030',
        weight=640,
        group='OpenSlides-Voting',
        subgroup='General'
    )
    yield ConfigVariable(
        name='voting_start_prompt',
        default_value=ugettext_noop('Please vote now!'),
        label='Voting start prompt (projector overlay message)',
        weight=650,
        group='OpenSlides-Voting',
        subgroup='General'
    )

    # Delegate board
    yield ConfigVariable(
        name='voting_show_delegate_board',
        default_value=True,
        input_type='boolean',
        label='Show delegate board',
        help_text='Show incoming votes on a delegate board on the projector.',
        weight=660,
        group='OpenSlides-Voting',
        subgroup='Projector delegate board'
    )
    yield ConfigVariable(
        name='voting_delegate_board_columns',
        default_value=10,
        input_type='integer',
        label='Delegate board columns',
        weight=670,
        group='OpenSlides-Voting',
        subgroup='Projector delegate board'
    )
    yield ConfigVariable(
        name='voting_delegate_board_name',
        default_value='short_name',
        input_type='choice',
        label='Delegate name format used for delegate table cells',
        choices=(
            {'value': 'short_name', 'display_name': 'Short name. Example: Smi,J'},
            {'value': 'last_name', 'display_name': 'Last name. Example: Smith'},
            {'value': 'full_name', 'display_name': 'Full name. Example: Smith John'},
        ),
        weight=680,
        group='OpenSlides-Voting',
        subgroup='Projector delegate board'
    )
    yield ConfigVariable(
        name='voting_anonymous',
        default_value=False,
        input_type='boolean',
        label='Vote anonymously',
        help_text='Keep individual voting behaviour secret on delegate board by using a single colour.',
        weight=690,
        group='OpenSlides-Voting',
        subgroup='Projector delegate board'
    )
