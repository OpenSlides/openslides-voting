from django.conf.urls import url

from . import views
from .votecollector import urls

urlpatterns = [
    url(r'^voting/attendance/shares/$',
        views.AttendanceView.as_view(),
        name='voting_attendance'),
] + urls.urlpatterns
