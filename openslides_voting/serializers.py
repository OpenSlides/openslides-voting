from openslides.utils.rest_api import ModelSerializer, JSONField, ValidationError

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
            'assignment_poll',
        )


class VotingControllerSerializer(ModelSerializer):
    class Meta:
        model = models.VotingController
        fields = (
            'id',
            'device_status',
            'voting_mode',
            'voting_target',
            'voting_duration',
            'votes_count',
            'votes_received',
            'is_voting',
            'principle',
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


class MotionAbsenteeVoteSerializer(ModelSerializer):
    class Meta:
        model = models.MotionAbsenteeVote
        fields = ('id', 'motion', 'delegate', 'vote', )

    def validate(self, data):
        if data['vote'] not in ('Y', 'N', 'A'):
            raise ValidationError({'detail': 'The vote intention for motions can only be Y, N or A.'})
        return data


class AssignmentAbsenteeVoteSerializer(ModelSerializer):
    class Meta:
        model = models.AssignmentAbsenteeVote
        fields = ('id', 'assignment', 'delegate', 'vote', )

    def validate(self, data):
        is_valid_int = False
        try:
            int_vote = int(data['vote'])
            if int_vote > 0:
                is_valid_int = True
        except:
            pass
        if data['vote'] not in ('Y', 'N', 'A') and not is_valid_int:
            raise ValidationError({'detail': 'The vote intention for assignments can only be Y, N, A or an integer greater then 0.'})
        return data


class MotionPollBallotSerializer(ModelSerializer):
    class Meta:
        model = models.MotionPollBallot
        fields = ('id', 'poll', 'delegate', 'vote', 'device', 'result_token', )


class MotionPollTypeSerializer(ModelSerializer):
    class Meta:
        model = models.MotionPollType
        fields = ('id', 'poll', 'type', )


class AssignmentPollBallotSerializer(ModelSerializer):
    vote = JSONField()
    class Meta:
        model = models.AssignmentPollBallot
        fields = ('id', 'poll', 'delegate', 'vote', 'device', 'result_token', )


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
