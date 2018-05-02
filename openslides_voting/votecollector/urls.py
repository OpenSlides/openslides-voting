from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views

urlpatterns = [
    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/$',
        views.SubmitVotes.as_view(),
        name='votingcontroller_votes'),
    url(r'^votingcontroller/votecollector/vote/(?P<poll_id>\d+)/$',
        csrf_exempt(views.SubmitVotes.as_view()), {
            'votecollector': True,
        },
        name='votingcontroller_votecollector_votes'),
]

def TODO():
    """
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
    """
