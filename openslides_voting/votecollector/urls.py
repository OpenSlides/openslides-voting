from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views

# Info: The client always has to give the poll id. THis isn't redundant to the
# poll id saved in the votingcontroller, because the server can check, if the request
# is really for the current poll. Maybe the request is late and the clients votes for
# the wrong poll. This must be permitted.

urlpatterns = [
    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/$',
        views.SubmitVotes.as_view(),
        name='votingcontroller_votes'),
    url(r'^votingcontroller/votecollector/vote/(?P<poll_id>\d+)/$',
        csrf_exempt(views.SubmitVotes.as_view()), {
            'votecollector': True,
        },
        name='votingcontroller_votecollector_votes'),
    url(r'^votingcontroller/candidate/(?P<poll_id>\d+)/$',
        views.SubmitCandidates.as_view(),
        name='votingcontroller_candidates'),
    url(r'^votingcontroller/votecollector/candidate/(?P<poll_id>\d+)/$',
        csrf_exempt(views.SubmitCandidates.as_view()), {
            'votecollector': True,
        },
        name='votingcontroller_votecollector_candidates'),
]

def TODO():
    """
    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/(?P<keypad_id>\d+)/$',
        csrf_exempt(views.VoteCallback.as_view()),
        name='votingcontroller_vote'),

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
