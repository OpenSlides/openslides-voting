from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views

# Info: The client has to always submit the poll id. This isn't redundant to the
# poll id saved in the votingcontroller, because the server can check, if the request
# is really for the current poll. Maybe the request is late and the clients votes for
# the wrong poll. This must be permitted.

urlpatterns = [
    url(r'^votingcontroller/vote/(?P<poll_id>\d+)/$',
        views.SubmitVotes.as_view()),
    url(r'^votingcontroller/votecollector/vote/(?P<poll_id>\d+)/$',
        csrf_exempt(views.SubmitVotes.as_view()), {
            'votecollector': True,
        }),
    url(r'^votingcontroller/candidate/(?P<poll_id>\d+)/$',
        views.SubmitCandidates.as_view()),
    url(r'^votingcontroller/votecollector/candidate/(?P<poll_id>\d+)/$',
        csrf_exempt(views.SubmitCandidates.as_view()), {
            'votecollector': True,
        }),
    url(r'^votingcontroller/votecollector/speaker/(?P<item_id>\d+)/(?P<keypad_number>\d+)/$',
        csrf_exempt(views.SubmitSpeaker.as_view())),
    url(r'^votingcontroller/votecollector/keypad/$',
        csrf_exempt(views.SubmitKeypads.as_view())),
]
