from openslides.utils.rest_api import ModelSerializer, JSONField

from . import models


class AuthorizedVotersSerializer(ModelSerializer):
    authorized_voters = JSONField()
    class Meta:
        model = models.AuthorizedVoters
        fields = (
                'id',
                'authorized_voters',
                'type',
                'motion_poll',
                'assignment_poll')


class VotingControllerSerializer(ModelSerializer):
    class Meta:
        model = models.VotingController
        fields = (
            'id',
            'device_status',
            'voting_mode',
            'voting_target',
            'voting_duration',
            'voters_count',
            'votes_received',
            'is_voting',
        )


class KeypadSerializer(ModelSerializer):
    class Meta:
        model = models.Keypad
        fields = ('id', 'number', 'user', 'battery_level', 'in_range', )


class VotingPrincipleSerializer(ModelSerializer):
    class Meta:
        model = models.VotingPrinciple
        fields = ('id', 'name', 'decimal_places', 'motions', 'assignments', )


class VotingShareSerializer(ModelSerializer):
    class Meta:
        model = models.VotingShare
        fields = ('id', 'delegate', 'principle', 'shares', )


class VotingProxySerializer(ModelSerializer):
    class Meta:
        model = models.VotingProxy
        fields = ('id', 'delegate', 'proxy', )


class AbsenteeVoteSerializer(ModelSerializer):
    class Meta:
        model = models.AbsenteeVote
        fields = ('id', 'motion', 'delegate', 'vote', )


class MotionPollBallotSerializer(ModelSerializer):
    class Meta:
        model = models.MotionPollBallot
        fields = ('id', 'poll', 'delegate', 'vote', )


class MotionPollTypeSerializer(ModelSerializer):
    class Meta:
        model = models.MotionPollType
        fields = ('id', 'poll', 'type', )


class AssignmentPollBallotSerializer(ModelSerializer):
    class Meta:
        model = models.AssignmentPollBallot
        fields = ('id', 'poll', 'delegate', 'vote', )


class AssignmentPollTypeSerializer(ModelSerializer):
    class Meta:
        model = models.AssignmentPollType
        fields = ('id', 'poll', 'type', )


class AttendanceLogSerializer(ModelSerializer):
    class Meta:
        model = models.AttendanceLog
        fields = ('id', 'message', 'created', )


class VotingTokenSerializer(ModelSerializer):
    class Meta:
        model = models.VotingToken
        fields = ('id', 'token', )
