from django.conf.urls import url

from . import views
from .votecollector import urls

urlpatterns = [
    url(r'^voting/attendance/shares/$',
        views.AttendanceView.as_view(),
        name='voting_attendance'),
    url(r'^voting/count/(?P<poll_id>\d+)/$',
        views.CountVotesView.as_view(),
        name='voting_count_votes')
] + urls.urlpatterns
