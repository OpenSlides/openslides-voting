from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views

urlpatterns = [
    url(r'^votecollector/device/$',
        views.DeviceStatus.as_view(),
        name='votecollector_device'),

    url(r'^votecollector/start_voting/(?P<id>\d+)/$',
        views.StartYNA.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll',
            'mode': 'YesNoAbstain',
            'resource': '/vote/'
        },
        name='votecollector_start_voting'),

    url(r'^votecollector/start_election/(?P<id>\d+)/(?P<options>\d+)/$',
        views.StartElection.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll',
            'mode': 'SingleDigit',
            'resource': '/candidate/'
        },
        name='votecollector_start_election'),

    url(r'^votecollector/start_election_one/(?P<id>\d+)/$',
        views.StartYNA.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll',
            'mode': 'YesNoAbstain',
            'resource': '/vote/'
        },
        name='votecollector_start_election_one'),

    url(r'^votecollector/start_speaker_list/(?P<id>\d+)/$',
        views.StartSpeakerList.as_view(), {
            'app': 'agenda',
            'model': 'Item',
            'mode': 'SpeakerList',
            'resource': '/speaker/'
        },
        name='votecollector_start_speaker_list'),

    url(r'^votecollector/start_ping/$',
        views.StartPing.as_view(), {
            'mode': 'Ping',
            'resource': '/keypad/'
        },
        name='votecollector_start_ping'),

    url(r'^votecollector/stop/$',
        views.StopVoting.as_view(),
        name='votecollector_stop'),

    url(r'^votecollector/clear_voting/(?P<id>\d+)/$',
        views.ClearVotes.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll'
        },
        name='votecollector_clear_voting'),

    url(r'^votecollector/clear_election/(?P<id>\d+)/$',
        views.ClearVotes.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll'
        },
        name='votecollector_clear_election'),

    url(r'^votecollector/status/$',
        views.VotingStatus.as_view(),
        name='votecollector_status'),

    url(r'^votecollector/result_voting/(?P<id>\d+)/$',
        views.VotingResult.as_view(), {
            'app': 'motions',
            'model': 'MotionPoll'
        },
        name='votecollector_result_yna'),

    url(r'^votecollector/result_election/(?P<id>\d+)/$',
        views.VotingResult.as_view(), {
            'app': 'assignments',
            'model': 'AssignmentPoll'
        },
        name='votecollector_result_election'),

    url(r'^votecollector/vote/(?P<poll_id>\d+)/$',
        csrf_exempt(views.Votes.as_view()),
        name='votecollector_votes'),

    url(r'^votecollector/vote/(?P<poll_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.VoteCallback.as_view()),
        name='votecollector_vote'),

    url(r'^votecollector/candidate/(?P<poll_id>\d+)/$',
        csrf_exempt(views.Candidates.as_view()),
        name='votecollector_candidates'),

    url(r'^votecollector/candidate/(?P<poll_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.CandidateCallback.as_view()),
        name='votecollector_candidate'),

    url(r'^votecollector/speaker/(?P<item_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.SpeakerCallback.as_view()),
        name='votecollector_speaker'),

    url(r'^votecollector/keypad/$',
        csrf_exempt(views.Keypads.as_view()),
        name='votecollector_keypads'),

    url(r'^votecollector/keypad/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.KeypadCallback.as_view()),
        name='votecollector_keypad'),
]
