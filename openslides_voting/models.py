from django.db import models
from django.utils.translation import ugettext as _
from jsonfield import JSONField

from openslides.assignments.models import Assignment, AssignmentPoll
from openslides.motions.models import Motion, MotionPoll
from openslides.users.models import User
from openslides.utils.models import RESTModelMixin

from .access_permissions import (
    AbsenteeVoteAccessPermissions,
    AssignmentPollBallotAccessPermissions,
    AssignmentPollTypeAccessPermissions,
    AttendanceLogAccessPermissions,
    KeypadAccessPermissions,
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
        return '%s, %s, %s' % (self.delegate, self.category, self.shares)


class VotingProxy(RESTModelMixin, models.Model):
    access_permissions = VotingProxyAccessPermissions()

    delegate = models.OneToOneField(User, on_delete=models.CASCADE)
    proxy = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mandates')

    class Meta:
        default_permissions = ()

    def __str__(self):
        return '%s >> %s' % (self.delegate, self.proxy)


# TODO: Same for assignments. Should we do this in a second model or foreign keys
# to motion and assignment in this model?
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
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    vote = models.CharField(max_length=1, blank=True)
    resultToken = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        unique_together = ('poll', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.poll, self.delegate, self.vote)


class AssignmentPollBallot(RESTModelMixin, models.Model):
    access_permissions = AssignmentPollBallotAccessPermissions()

    poll = models.ForeignKey(AssignmentPoll, on_delete=models.CASCADE)
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    vote = models.CharField(max_length=1, blank=True)
    resultToken = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        unique_together = ('poll', 'delegate')

    def __str__(self):
        return '%s, %s, %s' % (self.poll, self.delegate, self.vote)


class MotionPollType(RESTModelMixin, models.Model):
    access_permissions = MotionPollTypeAccessPermissions()

    poll = models.ForeignKey(MotionPoll, on_delete=models.CASCADE)
    type = models.CharField(max_length=128, default='analog')

    class Meta:
        default_permissions = ()


class AssignmentPollType(RESTModelMixin, models.Model):
    access_permissions = AssignmentPollTypeAccessPermissions()

    poll = models.ForeignKey(AssignmentPoll, on_delete=models.CASCADE)
    type = models.CharField(max_length=128, default='analog')

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

    token = models.CharField(max_length=128)

    class Meta:
        default_permissions = ()
