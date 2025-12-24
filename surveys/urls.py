"""
Survey API URL Configuration

RESTful routing for survey builder
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SurveyViewSet, SectionViewSet, FieldViewSet,
    FieldOptionViewSet, ConditionalLogicViewSet,
    FieldDependencyViewSet
)

# Create router for viewsets
router = DefaultRouter()
router.register(r'surveys', SurveyViewSet, basename='survey')
router.register(r'sections', SectionViewSet, basename='section')
router.register(r'fields', FieldViewSet, basename='field')
router.register(r'field-options', FieldOptionViewSet, basename='field-option')
router.register(r'conditional-logic', ConditionalLogicViewSet, basename='conditional-logic')
router.register(r'field-dependencies', FieldDependencyViewSet, basename='field-dependency')

app_name = 'surveys'

urlpatterns = [
    path('', include(router.urls)),
]
