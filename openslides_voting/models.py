from django.db import models
from django.utils.translation import ugettext as _
from jsonfield import JSONField

from openslides.motions.models import Category, Motion, MotionPoll
from openslides.users.models import User
from openslides.utils.models import RESTModelMixin

from .access_permissions import (
    AbsenteeVoteAccessPermissions,
    AttendanceLogAccessPermissions,
    KeypadAccessPermissions,
    MotionPollBallotAccessPermissions,
    VoteCollectorAccessPermissions,
    VotingShareAccessPermissions,
    VotingProxyAccessPermissions,
)


class VoteCollector(RESTModelMixin, models.Model):
    """
    VoteCollector model. Provides device and voting status information.
    Currently only one votecollector is supported (pk=1).
    """
    access_permissions = VoteCollectorAccessPermissions()

    device_status = models.CharField(max_length=200, default='No device')
    voting_mode = models.CharField(max_length=50, null=True)
    voting_target = models.IntegerField(default=0)
    voting_duration = models.IntegerField(default=0)
    voters_count = models.IntegerField(default=0)
    votes_received = models.IntegerField(default=0)
    is_voting = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()
        permissions = (
            ('can_manage', 'Can manage voting'),
        )

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


class VotingShare(RESTModelMixin, models.Model):
    access_permissions = VotingShareAccessPermissions()

    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shares')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    shares = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        default_permissions = ()
        unique_together = ('delegate', 'category')

    def __str__(self):
        return '%s, %s, %s' % (self.delegate, self.category, self.shares)


class VotingProxy(RESTModelMixin, models.Model):
    access_permissions = VotingProxyAccessPermissions()

    delegate = models.OneToOneField(User, on_delete=models.CASCADE)
    proxy = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mandates')

    class Meta:
        default_permissions = ()

    def __str__(self):
        return '%s >> %s' % (self.delegate, self.proxy)


class AbsenteeVote(RESTModelMixin, models.Model):
    access_permissions = AbsenteeVoteAccessPermissions()

    motion = models.ForeignKey(Motion, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE)
    vote = models.CharField(max_length=1)

    class Meta:
        default_permissions = ()
        unique_together = ('motion', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.motion, self.delegate, self.vote)


class MotionPollBallot(RESTModelMixin, models.Model):
    access_permissions = MotionPollBallotAccessPermissions()

    poll = models.ForeignKey(MotionPoll, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='delegate_set')
    vote = models.CharField(max_length=1, blank=True)

    class Meta:
        default_permissions = ()
        unique_together = ('poll', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.poll, self.delegate, self.vote)


class AttendanceLog(RESTModelMixin, models.Model):
    access_permissions = AttendanceLogAccessPermissions()

    message = JSONField()
    created = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        ordering = ['-created']

    def __str__(self):
        return '%s | %s' % (self.created.strftime('%Y-%m-%d %H:%M') if self.created else '-', self.message)


# TODO: Add voting timestamp to Poll model.
