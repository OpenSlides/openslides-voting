from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views

urlpatterns = [
    url(r'^votingcontroller/device/$',
        views.DeviceStatus.as_view(),
        name='votingcontroller_device'),

    url(r'^votingcontroller/start_voting/(?P<id>\d+)/$',
        views.StartYNA.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll',
            'mode': 'YesNoAbstain',
            'resource': '/vote/'
        },
        name='votingcontroller_start_voting'),

    url(r'^votingcontroller/start_election/(?P<id>\d+)/(?P<options>\d+)/$',
        views.StartElection.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll',
            'mode': 'SingleDigit',
            'resource': '/candidate/'
        },
        name='votingcontroller_start_election'),

    url(r'^votingcontroller/start_election_one/(?P<id>\d+)/$',
        views.StartYNA.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll',
            'mode': 'YesNoAbstain',
            'resource': '/vote/'
        },
        name='votingcontroller_start_election_one'),

    url(r'^votingcontroller/start_speaker_list/(?P<id>\d+)/$',
        views.StartSpeakerList.as_view(), {
            'app': 'agenda',
            'model': 'Item',
            'mode': 'SpeakerList',
            'resource': '/speaker/'
        },
        name='votingcontroller_start_speaker_list'),

    url(r'^votingcontroller/start_ping/$',
        views.StartPing.as_view(), {
            'mode': 'Ping',
            'resource': '/keypad/'
        },
        name='votingcontroller_start_ping'),

    url(r'^votingcontroller/stop/$',
        views.StopVoting.as_view(),
        name='votingcontroller_stop'),

    url(r'^votingcontroller/clear_voting/(?P<id>\d+)/$',
        views.ClearVotes.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll'
        },
        name='votingcontroller_clear_voting'),

    url(r'^votingcontroller/clear_election/(?P<id>\d+)/$',
        views.ClearVotes.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll'
        },
        name='votingcontroller_clear_election'),

    url(r'^votingcontroller/status/$',
        views.VotingStatus.as_view(),
        name='votingcontroller_status'),

    url(r'^votingcontroller/result_voting/(?P<id>\d+)/$',
        views.VotingResult.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll'
        },
        name='votingcontroller_result_yna'),

    url(r'^votingcontroller/result_election/(?P<id>\d+)/$',
        views.VotingResult.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll'
        },
        name='votingcontroller_result_election'),

    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/$',
        csrf_exempt(views.Votes.as_view()),
        name='votingcontroller_votes'),

    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.VoteCallback.as_view()),
        name='votingcontroller_vote'),

    url(r'^votingcontroller/candidate/(?P<poll_id>\d+)/$',
        csrf_exempt(views.Candidates.as_view()),
        name='votingcontroller_candidates'),

    url(r'^votingcontroller/candidate/(?P<poll_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.CandidateCallback.as_view()),
        name='votingcontroller_candidate'),

    url(r'^votingcontroller/speaker/(?P<item_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.SpeakerCallback.as_view()),
        name='votingcontroller_speaker'),

    url(r'^votingcontroller/keypad/$',
        csrf_exempt(views.Keypads.as_view()),
        name='votingcontroller_keypads'),

    url(r'^votingcontroller/keypad/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.KeypadCallback.as_view()),
        name='votingcontroller_keypad'),
]
