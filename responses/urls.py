"""
URL Configuration for Response Submission API
"""

from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ResponseSubmissionViewSet

app_name = 'responses'

# Manual URL patterns for custom actions
urlpatterns = [
    path('start/', ResponseSubmissionViewSet.as_view({'post': 'start_session'}), name='start-session'),
    path('submit-incremental/', ResponseSubmissionViewSet.as_view({'post': 'submit_incremental'}), name='submit-incremental'),
    path('submit-final/', ResponseSubmissionViewSet.as_view({'post': 'submit_final'}), name='submit-final'),
    path('validate/', ResponseSubmissionViewSet.as_view({'post': 'validate_responses'}), name='validate'),
    path('resume/<str:token>/', ResponseSubmissionViewSet.as_view({'get': 'resume'}), name='resume'),
    path('<int:pk>/', ResponseSubmissionViewSet.as_view({'get': 'retrieve'}), name='retrieve'),
]
