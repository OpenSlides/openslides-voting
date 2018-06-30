import random

from django.db import models
from django.utils.translation import ugettext as _
from jsonfield import JSONField

from openslides.assignments.models import Assignment, AssignmentPoll
from openslides.motions.models import Motion, MotionPoll
from openslides.users.models import User
from openslides.utils.exceptions import OpenSlidesError
from openslides.utils.models import RESTModelMixin

from .access_permissions import (
    AssignmentAbsenteeVoteAccessPermissions,
    AssignmentPollBallotAccessPermissions,
    AssignmentPollTypeAccessPermissions,
    AttendanceLogAccessPermissions,
    AuthorizedVotersAccessPermissions,
    KeypadAccessPermissions,
    MotionAbsenteeVoteAccessPermissions,
    MotionPollBallotAccessPermissions,
    MotionPollTypeAccessPermissions,
    VotingTokenAccessPermissions,
    VotingControllerAccessPermissions,
    VotingPrincipleAccessPermissions,
    VotingShareAccessPermissions,
    VotingProxyAccessPermissions,
)


# Workaroud, that we cannot add a foreign key to motions or assignment to VotingPrinciple.
# See https://github.com/adsworth/django-onetomany for more information
class OneToManyField(models.ManyToManyField):
    """
    A forgein key field that behaves just like djangos ManyToMany field,
    the only difference is that an instance of the other side can only be
    related to one instance of your side. Also see the test cases.
    """
    def contribute_to_class(self, cls, name):
        # Check if the intermediate model will be auto created.
        # The intermediate m2m model is not auto created if:
        #  1) There is a manually specified intermediate, or
        #  2) The class owning the m2m field is abstract.
        #  3) The class owning the m2m field has been swapped out.
        auto_intermediate = False
        if not self.rel.through and not cls._meta.abstract and not cls._meta.swapped:
            auto_intermediate = True

        #One call super contribute_to_class and have django create the intermediate model.
        super(OneToManyField, self).contribute_to_class(cls, name)

        if auto_intermediate == True:
            #Set unique_together to the 'to' relationship, this ensures a OneToMany relationship.
            self.rel.through._meta.unique_together = ((self.rel.through._meta.unique_together[0][1],),)


class VotingPrinciple(RESTModelMixin, models.Model):
    access_permissions = VotingPrincipleAccessPermissions()

    name = models.CharField(max_length=128, unique=True)
    decimal_places = models.PositiveIntegerField()

    motions = OneToManyField(Motion, blank=True)
    assignments = OneToManyField(Assignment, blank=True)

    class Meta:
        default_permissions = ()


class VotingShare(RESTModelMixin, models.Model):
    access_permissions = VotingShareAccessPermissions()

    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shares')
    principle = models.ForeignKey(VotingPrinciple, on_delete=models.CASCADE, null=True)
    shares = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        default_permissions = ()
        unique_together = ('delegate', 'principle')

    def __str__(self):
        return '%s, %s, %s' % (self.delegate, self.principle, self.shares)


class AuthorizedVoters(RESTModelMixin, models.Model):
    access_permissions = AuthorizedVotersAccessPermissions()
    authorized_voters = JSONField(default=[])

    motion_poll = models.OneToOneField(MotionPoll, on_delete=models.SET_NULL, null=True, blank=True)
    assignment_poll = models.OneToOneField(AssignmentPoll, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.CharField(max_length=128, default='analog')

    class Meta:
        default_permissions = ()

    def delete(self, *args, **kwargs):
        raise OpenSlidesError('The AuthorizedVoters object cannot be deleted.')

    @classmethod
    def set_voting(cls, delegates, voting_type, motion_poll=None, assignment_poll=None):
        instance = cls.objects.get()
        instance.authorized_voters = delegates
        instance.type = voting_type
        instance.motion_poll = motion_poll
        instance.assignment_poll = assignment_poll
        instance.save()

    @classmethod
    def update_delegates(cls, delegates):
        instance = cls.objects.get()
        print(delegates)
        instance.authorized_voters = delegates
        print(instance.authorized_voters)
        instance.save()

    @classmethod
    def clear_voting(cls):
        cls.set_voting([], '', motion_poll=None, assignment_poll=None)


class VotingController(RESTModelMixin, models.Model):
    """
    VotingController model. Provides device and voting status information.
    Currently only one votingcontroller is supported (pk=1).
    """
    access_permissions = VotingControllerAccessPermissions()

    device_status = models.CharField(max_length=200, default='No device')
    voting_mode = models.CharField(max_length=50, null=True)
    voting_target = models.IntegerField(default=0)
    voting_duration = models.IntegerField(default=0)
    votes_count = models.IntegerField(default=0)
    votes_received = models.IntegerField(default=0)
    is_voting = models.BooleanField(default=False)
    principle = models.OneToOneField(VotingPrinciple, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        default_permissions = ()
        permissions = (
            ('can_manage', 'Can manage voting'),
            ('can_see_token_voting', 'Can see the token voting interface'),
            ('can_vote', 'Can vote'),
        )

    def delete(self, *args, **kwargs):
        raise OpenSlidesError('The VotingController object cannot be deleted.')

    def __str__(self):
        return self.device_status


class Keypad(RESTModelMixin, models.Model):
    access_permissions = KeypadAccessPermissions()

    user = models.OneToOneField(User, null=True, blank=True)
    number = models.IntegerField(unique=True)
    battery_level = models.SmallIntegerField(default=-1)  # -1 = unknown
    in_range = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()

    def __str__(self):
        if self.user is not None:
            return _('Keypad %(kp)d (%(user)s)') % {
                'kp': self.number, 'user': self.user}
        return _('Keypad %d') % self.number


class VotingProxy(RESTModelMixin, models.Model):
    access_permissions = VotingProxyAccessPermissions()

    delegate = models.OneToOneField(User, on_delete=models.CASCADE)
    proxy = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mandates')

    class Meta:
        default_permissions = ()

    def __str__(self):
        return '%s >> %s' % (self.delegate, self.proxy)


class MotionAbsenteeVote(RESTModelMixin, models.Model):
    access_permissions = MotionAbsenteeVoteAccessPermissions()

    motion = models.ForeignKey(Motion, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE)
    vote = models.CharField(max_length=1)

    class Meta:
        default_permissions = ()
        unique_together = ('motion', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.motion, self.delegate, self.vote)


class AssignmentAbsenteeVote(RESTModelMixin, models.Model):
    access_permissions = AssignmentAbsenteeVoteAccessPermissions()

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE)
    vote = models.CharField(max_length=255)

    class Meta:
        default_permissions = ()
        unique_together = ('assignment', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.assignment, self.delegate, self.vote)


class PollBallot:
    @classmethod
    def get_next_result_token(cls, used_tokens):
        if len(used_tokens) == 0:
            return random.randint(100, 999)

        max_token_value = max(used_tokens)
        digits = len(str(max_token_value))

        max_token_count = 10 ** digits - 101  # the 101 is for the first 100 and the
        # last one. So for e.g. 4 digits, the range would be from 100 to 9999,
        # so 10000-101 = 9899 possible tokens

        if len(used_tokens) >= max_token_count:
            # We need to have one more digit.
            return random.randint(10 ** digits, 10 ** (digits+1) - 1)

        not_used_tokens = [t for t in range(100, 10**digits) if t not in used_tokens]
        return random.choice(not_used_tokens)


class MotionPollBallot(RESTModelMixin, models.Model, PollBallot):
    access_permissions = MotionPollBallotAccessPermissions()

    poll = models.ForeignKey(MotionPoll, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    vote = models.CharField(max_length=1, blank=True)
    result_token = models.PositiveIntegerField()
    is_dummy = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return '%s, %s, %s' % (self.poll, self.delegate, self.vote)


class AssignmentPollBallot(RESTModelMixin, models.Model, PollBallot):
    access_permissions = AssignmentPollBallotAccessPermissions()

    poll = models.ForeignKey(AssignmentPoll, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    vote = JSONField(default={})
    result_token = models.PositiveIntegerField()
    is_dummy = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return '%s, %s, %s' % (self.poll, self.delegate, self.vote)


POLLTYPES = [
    ('analog', 'Analog voting'),
    ('named_electronic', 'Named electronic voting'),
    ('token_based_electronic', 'Token-based electronic voting'),
    ('votecollector', 'VoteCollector'),
    ('votecollector_anonym', 'VoteCollector anonym')
]


class MotionPollType(RESTModelMixin, models.Model):
    access_permissions = MotionPollTypeAccessPermissions()

    poll = models.OneToOneField(MotionPoll, on_delete=models.CASCADE)
    type = models.CharField(max_length=32, default=POLLTYPES[0][0], choices=POLLTYPES)

    class Meta:
        default_permissions = ()


class AssignmentPollType(RESTModelMixin, models.Model):
    access_permissions = AssignmentPollTypeAccessPermissions()

    poll = models.OneToOneField(AssignmentPoll, on_delete=models.CASCADE)
    type = models.CharField(max_length=32, default=POLLTYPES[0][0], choices=POLLTYPES)

    class Meta:
        default_permissions = ()


# TODO: Add voting timestamp to Poll model.
class AttendanceLog(RESTModelMixin, models.Model):
    access_permissions = AttendanceLogAccessPermissions()

    message = JSONField()
    created = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        ordering = ['-created']

    def __str__(self):
        return '%s | %s' % (self.created.strftime('%Y-%m-%d %H:%M') if self.created else '-', self.message)


class VotingToken(RESTModelMixin, models.Model):
    access_permissions = VotingTokenAccessPermissions()

    token = models.CharField(max_length=128, unique=True)

    class Meta:
        default_permissions = ()
