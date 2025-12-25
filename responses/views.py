"""
Response Submission Views

Handles survey response submission with:
- Incremental (step-by-step) responses
- Partial progress saving
- Resume capability via token
- Final immutable submission
- High concurrency support
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response as DRFResponse
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.cache import cache
from django.db.models import F
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import hashlib
import secrets

from .models import SurveyResponse, SurveyResponseItem, PartialResponse
from .serializers import (
    IncrementalSubmissionSerializer,
    FinalSubmissionSerializer,
    PartialResponseSerializer,
    ResponseRetrievalSerializer,
    ResponseValidationSerializer
)
from surveys.models import Survey, Field


class ResponseSubmissionViewSet(viewsets.ViewSet):
    """
    ViewSet for handling survey response submissions.
    
    Endpoints:
    - POST /responses/start/ - Start new response session
    - POST /responses/submit-incremental/ - Submit partial answers
    - POST /responses/submit-final/ - Complete and finalize submission
    - POST /responses/validate/ - Validate without saving
    - GET /responses/resume/{token}/ - Resume partial response
    - GET /responses/{id}/ - Retrieve completed response
    """
    
    permission_classes = [AllowAny]  # Public surveys allow anonymous responses
    
    @extend_schema(
        summary="Start Response Session",
        description="Initialize a new survey response session with a unique session ID",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'survey_id': {'type': 'integer', 'description': 'Survey ID to respond to'},
                    'user_id': {'type': 'integer', 'description': 'User ID (optional for anonymous)', 'nullable': True}
                },
                'required': ['survey_id']
            }
        },
        responses={
            201: {
                'description': 'Session started successfully',
                'content': {
                    'application/json': {
                        'example': {
                            'session_id': 'abc123xyz...',
                            'survey_id': 1,
                            'start_time': '2025-01-15T10:30:00Z'
                        }
                    }
                }
            },
            404: {'description': 'Survey not found or not published'}
        },
        tags=['Response Submission']
    )
    @action(detail=False, methods=['post'], url_path='start')
    def start_session(self, request):
        """Start a new response session."""
        survey_id = request.data.get('survey_id')
        user_id = request.data.get('user_id')
        
        if not survey_id:
            return DRFResponse(
                {'error': 'survey_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify survey exists and is published
        try:
            survey = Survey.objects.get(id=survey_id, status='published')
        except Survey.DoesNotExist:
            return DRFResponse(
                {'error': 'Survey not found or not published'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Generate unique session ID
        session_id = secrets.token_urlsafe(32)
        
        # Store session in cache (24 hour expiry)
        cache_key = f'survey_session:{session_id}'
        cache.set(cache_key, {
            'survey_id': survey_id,
            'user_id': user_id,
            'start_time': timezone.now().isoformat(),
            'responses': {}
        }, timeout=86400)
        
        return DRFResponse({
            'session_id': session_id,
            'survey_id': survey_id,
            'start_time': timezone.now().isoformat()
        }, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="Submit Incremental Response",
        description="Save partial survey responses and get a resume token. Supports merging with existing partial responses.",
        request=IncrementalSubmissionSerializer,
        responses={
            200: {
                'description': 'Partial response saved',
                'content': {
                    'application/json': {
                        'example': {
                            'status': 'saved',
                            'resume_token': 'xyz789abc...',
                            'responses_saved': 5,
                            'total_responses': 12,
                            'can_submit': False
                        }
                    }
                }
            },
            400: {'description': 'Validation error'},
            404: {'description': 'Resume token not found'},
            410: {'description': 'Resume token expired'}
        },
        tags=['Response Submission']
    )
    @action(detail=False, methods=['post'], url_path='submit-incremental')
    def submit_incremental(self, request):
        """Submit incremental (partial) responses."""
        serializer = IncrementalSubmissionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return DRFResponse(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        survey_id = validated_data['survey_id']
        session_id = validated_data.get('session_id')
        resume_token = validated_data.get('resume_token')
        responses = validated_data['responses']
        
        # Convert responses to dict
        response_dict = {r['field_id']: r['value'] for r in responses}
        
        try:
            with transaction.atomic():
                # Get or create partial response
                if resume_token:
                    # Resume existing partial response
                    try:
                        partial = PartialResponse.objects.select_for_update().get(
                            resume_token=resume_token,
                            survey_id=survey_id
                        )
                        
                        # Check if expired
                        if partial.expires_at and partial.expires_at < timezone.now():
                            return DRFResponse(
                                {'error': 'Resume token expired'},
                                status=status.HTTP_410_GONE
                            )
                        
                        # Merge with existing responses
                        existing_responses = partial.responses or {}
                        existing_responses.update(response_dict)
                        partial.responses = existing_responses
                        partial.updated_at = timezone.now()
                        partial.save()
                        
                    except PartialResponse.DoesNotExist:
                        return DRFResponse(
                            {'error': 'Invalid resume token'},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    # Create new partial response
                    partial = PartialResponse.objects.create(
                        survey_id=survey_id,
                        session_id=session_id or secrets.token_urlsafe(16),
                        responses=response_dict,
                        resume_token=secrets.token_urlsafe(32),
                        expires_at=timezone.now() + timezone.timedelta(days=7)
                    )
                
                # Check if all required fields are filled
                can_submit = self._check_can_submit(survey_id, partial.responses)
                
                return DRFResponse({
                    'status': 'saved',
                    'resume_token': partial.resume_token,
                    'responses_saved': len(response_dict),
                    'total_responses': len(partial.responses),
                    'can_submit': can_submit
                }, status=status.HTTP_200_OK)
                
        except IntegrityError as e:
            return DRFResponse(
                {'error': 'Database error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Submit Final Response",
        description="Complete and finalize survey submission. Creates immutable response record with duplicate detection.",
        request=FinalSubmissionSerializer,
        responses={
            201: {
                'description': 'Response submitted successfully',
                'content': {
                    'application/json': {
                        'example': {
                            'status': 'submitted',
                            'response_id': 123,
                            'submission_time': '2025-01-15T11:45:00Z'
                        }
                    }
                }
            },
            400: {'description': 'Validation error - incomplete or invalid responses'},
            409: {'description': 'Duplicate submission detected'},
            500: {'description': 'Server error during submission'}
        },
        tags=['Response Submission']
    )
    @action(detail=False, methods=['post'], url_path='submit-final')
    def submit_final(self, request):
        """Submit final (complete) response."""
        serializer = FinalSubmissionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return DRFResponse(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        survey_id = validated_data['survey_id']
        session_id = validated_data.get('session_id')
        resume_token = validated_data.get('resume_token')
        responses = validated_data['responses']
        user_id = validated_data.get('user_id')
        
        # Generate idempotency key to prevent duplicate submissions
        idempotency_key = self._generate_idempotency_key(
            survey_id, session_id or resume_token, responses
        )
        
        # Check if already submitted (race condition protection)
        cache_key = f'submission:{idempotency_key}'
        if cache.get(cache_key):
            # Already submitted within last 5 minutes
            return DRFResponse(
                {'error': 'Duplicate submission detected'},
                status=status.HTTP_409_CONFLICT
            )
        
        try:
            with transaction.atomic():
                # Set cache lock (5 minute expiry)
                cache.set(cache_key, True, timeout=300)
                
                # Create response record
                survey_response = SurveyResponse.objects.create(
                    survey_id=survey_id,
                    user_id=user_id,
                    session_id=session_id or idempotency_key[:32],
                    is_complete=True,
                    start_time=timezone.now(),
                    completion_time=timezone.now()
                )
                
                # Create response items
                response_items = []
                for response in responses:
                    response_items.append(
                        SurveyResponseItem(
                            response=survey_response,
                            field_id=response['field_id'],
                            value=response['value']
                        )
                    )
                
                # Bulk create all items
                SurveyResponseItem.objects.bulk_create(
                    response_items,
                    batch_size=100
                )
                
                # Delete partial response if exists
                if resume_token:
                    PartialResponse.objects.filter(
                        resume_token=resume_token,
                        survey_id=survey_id
                    ).delete()
                
                # Clear session cache
                if session_id:
                    cache.delete(f'survey_session:{session_id}')
                
                return DRFResponse({
                    'status': 'submitted',
                    'response_id': survey_response.id,
                    'submission_time': survey_response.completion_time.isoformat()
                }, status=status.HTTP_201_CREATED)
                
        except IntegrityError as e:
            # Handle race condition - another request created response first
            return DRFResponse(
                {'error': 'Submission already processed'},
                status=status.HTTP_409_CONFLICT
            )
        except Exception as e:
            # Release cache lock on error
            cache.delete(cache_key)
            return DRFResponse(
                {'error': f'Submission failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="Validate Responses",
        description="Validate survey responses without saving. Useful for real-time client-side validation.",
        request=ResponseValidationSerializer,
        responses={
            200: {
                'description': 'Validation result',
                'content': {
                    'application/json': {
                        'examples': {
                            'valid': {
                                'value': {'valid': True, 'errors': {}}
                            },
                            'invalid': {
                                'value': {
                                    'valid': False,
                                    'errors': {
                                        'responses': {
                                            '0': {'field_id': ['Required field']}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        tags=['Response Submission']
    )
    @action(detail=False, methods=['post'], url_path='validate')
    def validate_responses(self, request):
        """Validate responses without saving."""
        serializer = ResponseValidationSerializer(data=request.data)
        
        if serializer.is_valid():
            return DRFResponse({
                'valid': True,
                'errors': {}
            }, status=status.HTTP_200_OK)
        else:
            return DRFResponse({
                'valid': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Resume Partial Response",
        description="Load a previously saved partial response using its resume token",
        parameters=[
            OpenApiParameter(
                name='token',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description='Resume token from previous incremental submission'
            )
        ],
        responses={
            200: {
                'description': 'Partial response loaded',
                'content': {
                    'application/json': {
                        'example': {
                            'survey_id': 1,
                            'responses': {
                                '101': 'John Doe',
                                '102': 'john@example.com',
                                '103': 25
                            },
                            'expires_at': '2025-01-22T10:30:00Z',
                            'updated_at': '2025-01-15T14:20:00Z'
                        }
                    }
                }
            },
            404: {'description': 'Invalid resume token'},
            410: {'description': 'Resume token expired'}
        },
        tags=['Response Submission']
    )
    @action(detail=False, methods=['get'], url_path='resume/(?P<token>[^/.]+)')
    def resume(self, request, token=None):
        """Resume partial response using token."""
        try:
            partial = PartialResponse.objects.get(resume_token=token)
            
            # Check if expired
            if partial.expires_at and partial.expires_at < timezone.now():
                partial.delete()
                return DRFResponse(
                    {'error': 'Resume token expired'},
                    status=status.HTTP_410_GONE
                )
            
            return DRFResponse({
                'survey_id': partial.survey.id,
                'responses': partial.responses,
                'expires_at': partial.expires_at.isoformat() if partial.expires_at else None,
                'updated_at': partial.updated_at.isoformat()
            }, status=status.HTTP_200_OK)
            
        except PartialResponse.DoesNotExist:
            return DRFResponse(
                {'error': 'Invalid or expired resume token'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @extend_schema(
        summary="Retrieve Completed Response",
        description="Get a completed survey response by ID. Requires authentication if response belongs to a user.",
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Response ID'
            )
        ],
        responses={
            200: {
                'description': 'Response retrieved',
                'content': {
                    'application/json': {
                        'example': {
                            'id': 123,
                            'survey_id': 1,
                            'user_id': 5,
                            'is_complete': True,
                            'start_time': '2025-01-15T10:00:00Z',
                            'completion_time': '2025-01-15T10:15:00Z',
                            'items': [
                                {'field_id': 101, 'value': 'John Doe'},
                                {'field_id': 102, 'value': 'john@example.com'}
                            ]
                        }
                    }
                }
            },
            403: {'description': 'Permission denied'},
            404: {'description': 'Response not found'}
        },
        tags=['Response Submission']
    )
    def retrieve(self, request, pk=None):
        """Retrieve completed response by ID."""
        try:
            response = SurveyResponse.objects.select_related('survey').get(id=pk)
            
            # Check permissions
            if response.user and response.user != request.user:
                if not request.user.is_staff:
                    return DRFResponse(
                        {'error': 'Permission denied'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            serializer = ResponseRetrievalSerializer(response)
            return DRFResponse(serializer.data, status=status.HTTP_200_OK)
            
        except SurveyResponse.DoesNotExist:
            return DRFResponse(
                {'error': 'Response not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Helper methods
    def _check_can_submit(self, survey_id, responses):
        """Check if response has all required fields to be submitted."""
        from surveys.logic_engine import LogicEngine
        from surveys.models import ConditionalLogic
        
        response_map = {str(k): v for k, v in responses.items()}
        
        logic_rules = ConditionalLogic.objects.filter(
            trigger_field__section__survey_id=survey_id
        ).select_related('trigger_field', 'target_field')
        
        engine = LogicEngine(response_map)
        
        all_field_ids = set(
            Field.objects.filter(
                section__survey_id=survey_id
            ).values_list('id', flat=True)
        )
        visible_fields = all_field_ids.copy()
        
        for rule in logic_rules:
            try:
                result = engine.evaluate(rule.condition)
                if rule.action == 'hide' and result:
                    visible_fields.discard(rule.target_field.id)
                elif rule.action == 'show' and not result:
                    visible_fields.discard(rule.target_field.id)
            except:
                pass
        
        required_fields = Field.objects.filter(
            section__survey_id=survey_id,
            is_required=True,
            id__in=visible_fields
        ).values_list('id', flat=True)
        
        for field_id in required_fields:
            if str(field_id) not in response_map or not response_map[str(field_id)]:
                return False
        
        return True
    
    def _generate_idempotency_key(self, survey_id, session_id, responses):
        """Generate idempotency key for duplicate detection."""
        sorted_responses = sorted(
            [(r['field_id'], r['value']) for r in responses],
            key=lambda x: x[0]
        )
        
        key_data = f"{survey_id}:{session_id}:{sorted_responses}"
        return hashlib.sha256(key_data.encode()).hexdigest()
