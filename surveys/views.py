"""
Survey API Views

RESTful viewsets for survey builder with step-by-step creation.
Designed for frontend builders like Typeform/SurveyMonkey.
"""

from rest_framework import viewsets, status,serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import (
    Survey, Section, Field, FieldOption,
    ConditionalLogic, FieldDependency
)
from .serializers import (
    SurveyListSerializer, SurveyDetailSerializer,
    SurveyCreateSerializer, SurveyUpdateSerializer,
    SurveyPublishSerializer, SurveyVersionSerializer,
    SectionSerializer, SectionCreateSerializer,
    FieldSerializer, FieldCreateSerializer,
    FieldOptionSerializer, ConditionalLogicSerializer,
    FieldDependencySerializer, BulkOperationSerializer
)


@extend_schema_view(
    list=extend_schema(
        summary="List all surveys",
        description="Get a paginated list of surveys with filtering and search capabilities",
        parameters=[
            OpenApiParameter(name='status', description='Filter by status', type=OpenApiTypes.STR, enum=['draft', 'published', 'archived']),
            OpenApiParameter(name='active_only', description='Show only active versions', type=OpenApiTypes.BOOL),
            OpenApiParameter(name='search', description='Search in title and description', type=OpenApiTypes.STR),
        ],
        tags=['Surveys'],
    ),
    create=extend_schema(
        summary="Create a new survey",
        description="Create a new survey in draft status",
        tags=['Surveys'],
    ),
    retrieve=extend_schema(
        summary="Get survey details",
        description="Get full survey details including sections, fields, and options",
        tags=['Surveys'],
    ),
    update=extend_schema(
        summary="Update survey",
        description="Update survey metadata (title, description, etc.)",
        tags=['Surveys'],
    ),
    partial_update=extend_schema(
        summary="Partially update survey",
        description="Update specific survey fields",
        tags=['Surveys'],
    ),
    destroy=extend_schema(
        summary="Delete survey",
        description="Soft delete (archive) a survey",
        tags=['Surveys'],
    ),
)
class SurveyViewSet(viewsets.ModelViewSet):
    """
    Survey CRUD with versioning and publishing
    
    Endpoints:
    - GET /surveys/ - List surveys
    - POST /surveys/ - Create survey
    - GET /surveys/{id}/ - Get survey detail
    - PATCH /surveys/{id}/ - Update survey metadata
    - DELETE /surveys/{id}/ - Delete survey (soft delete)
    - POST /surveys/{id}/publish/ - Publish survey
    - POST /surveys/{id}/unpublish/ - Unpublish survey
    - POST /surveys/{id}/archive/ - Archive survey
    - POST /surveys/{id}/create_version/ - Create new version
    - GET /surveys/{id}/preview/ - Preview survey structure
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter surveys by tenant and user permissions
        Optimize queries with prefetch_related
        """
        user = self.request.user
        queryset = Survey.objects.select_related('created_by').prefetch_related(
            'sections',
            'sections__fields',
            'sections__fields__options'
        )
        
        # Filter by tenant if multi-tenant
        if hasattr(user, 'tenant_id'):
            queryset = queryset.filter(tenant_id=user.tenant_id)
        
        # Filter by status if requested
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by active versions only
        active_only = self.request.query_params.get('active_only', 'false')
        if active_only.lower() == 'true':
            queryset = queryset.filter(is_active_version=True)
        
        # Filter by search query
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return SurveyListSerializer
        elif self.action == 'create':
            return SurveyCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return SurveyUpdateSerializer
        elif self.action == 'publish':
            return SurveyPublishSerializer
        elif self.action == 'create_version':
            return SurveyVersionSerializer
        else:
            return SurveyDetailSerializer
    
    def perform_destroy(self, instance):
        """Soft delete - archive instead of delete"""
        instance.status = 'archived'
        instance.save()
    
    @extend_schema(
        summary="Publish survey",
        description="Publish a draft survey after validation. Published surveys cannot be edited.",
        request=SurveyPublishSerializer,
        responses={200: SurveyDetailSerializer},
        tags=['Surveys'],
    )
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """
        Publish a draft survey
        
        Validates survey structure before publishing.
        """
        survey = self.get_object()
        serializer = SurveyPublishSerializer(instance=survey, data={})
        
        if serializer.is_valid():
            survey.status = 'published'
            survey.save()
            
            return Response({
                'status': 'success',
                'message': 'Survey published successfully',
                'data': SurveyDetailSerializer(survey).data
            })
        
        return Response(
            {'status': 'error', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @extend_schema(
        summary="Unpublish survey",
        description="Unpublish a published survey and set it back to draft status",
        responses={200: SurveyDetailSerializer},
        tags=['Surveys'],
    )
    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Unpublish a survey (set to draft)"""
        survey = self.get_object()
        
        if survey.status != 'published':
            return Response(
                {'status': 'error', 'message': 'Survey is not published'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        survey.status = 'draft'
        survey.save()
        
        return Response({
            'status': 'success',
            'message': 'Survey unpublished successfully',
            'data': SurveyDetailSerializer(survey).data
        })
    
    @extend_schema(
        summary="Archive survey",
        description="Archive a survey (soft delete)",
        responses={200: SurveyDetailSerializer},
        tags=['Surveys'],
    )
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a survey"""
        survey = self.get_object()
        survey.status = 'archived'
        survey.save()
        
        return Response({
            'status': 'success',
            'message': 'Survey archived successfully'
        })
    
    @extend_schema(
        summary="Create new version",
        description="Create a new version of a published survey. Optionally copy the existing structure.",
        request=SurveyVersionSerializer,
        responses={201: SurveyDetailSerializer},
        tags=['Surveys'],
    )
    @action(detail=True, methods=['post'])
    def create_version(self, request, pk=None):
        """
        Create new version of published survey
        
        Copies structure if copy_structure=true
        """
        survey = self.get_object()
        serializer = SurveyVersionSerializer(instance=survey, data=request.data)
        
        if serializer.is_valid():
            copy_structure = serializer.validated_data.get('copy_structure', True)
            
            with transaction.atomic():
                new_version = survey.create_new_version(
                    user=request.user,
                    copy_structure=copy_structure
                )
            
            return Response({
                'status': 'success',
                'message': 'New version created successfully',
                'data': SurveyDetailSerializer(new_version).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(
            {'status': 'error', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @extend_schema(
        summary="Preview survey",
        description="Get simplified survey structure for frontend preview/rendering",
        responses={200: OpenApiTypes.OBJECT},
        tags=['Surveys'],
    )
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """
        Get survey structure for preview
        
        Returns simplified JSON structure for frontend rendering
        """
        survey = self.get_object()
        
        preview_data = {
            'id': survey.id,
            'title': survey.title,
            'description': survey.description,
            'version': survey.version,
            'sections': []
        }
        
        for section in survey.sections.all().order_by('order'):
            section_data = {
                'id': section.id,
                'title': section.title,
                'description': section.description,
                'order': section.order,
                'fields': []
            }
            
            for field in section.fields.all().order_by('order'):
                field_data = {
                    'id': field.id,
                    'label': field.label,
                    'type': field.field_type,
                    'description': field.description,
                    'placeholder': field.placeholder,
                    'required': field.is_required,
                    'order': field.order
                }
                
                # Add options for choice fields
                if field.field_type in ['single_choice', 'multiple_choice', 'dropdown']:
                    field_data['options'] = [
                        {
                            'id': opt.id,
                            'label': opt.label,
                            'value': opt.value,
                            'order': opt.order
                        }
                        for opt in field.options.all().order_by('order')
                    ]
                
                # Add validation rules
                if field.min_value or field.max_value:
                    field_data['validation'] = {}
                    if field.min_value:
                        field_data['validation']['min'] = field.min_value
                    if field.max_value:
                        field_data['validation']['max'] = field.max_value
                
                section_data['fields'].append(field_data)
            
            preview_data['sections'].append(section_data)
        
        return Response(preview_data)


@extend_schema_view(
    list=extend_schema(
        summary="List sections",
        description="Get all sections for a survey",
        parameters=[
            OpenApiParameter(name='survey', description='Filter by survey ID', type=OpenApiTypes.INT),
        ],
        tags=['Sections'],
    ),
    create=extend_schema(
        summary="Create section",
        description="Create a new section in a survey",
        tags=['Sections'],
    ),
    retrieve=extend_schema(
        summary="Get section details",
        description="Get section details including fields",
        tags=['Sections'],
    ),
    update=extend_schema(
        summary="Update section",
        description="Update section properties",
        tags=['Sections'],
    ),
    destroy=extend_schema(
        summary="Delete section",
        description="Delete a section and all its fields",
        tags=['Sections'],
    ),
)
class SectionViewSet(viewsets.ModelViewSet):
    """
    Section CRUD for survey builder
    
    Endpoints:
    - GET /sections/ - List sections (filtered by survey)
    - POST /sections/ - Create section
    - GET /sections/{id}/ - Get section detail
    - PATCH /sections/{id}/ - Update section
    - DELETE /sections/{id}/ - Delete section
    - POST /sections/bulk/ - Bulk operations (reorder, delete)
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter sections by survey"""
        queryset = Section.objects.select_related('survey').prefetch_related(
            'fields', 'fields__options'
        )
        
        survey_id = self.request.query_params.get('survey_id')
        if survey_id:
            queryset = queryset.filter(survey_id=survey_id)
        
        return queryset.order_by('order')
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action in ['create', 'update', 'partial_update']:
            return SectionCreateSerializer
        return SectionSerializer
    
    def perform_create(self, serializer):
        """Validate survey is editable"""
        survey = serializer.validated_data['survey']
        if survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot add sections to published survey"
            )
        serializer.save()
    
    def perform_update(self, serializer):
        """Validate survey is editable"""
        section = self.get_object()
        if section.survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot update sections in published survey"
            )
        serializer.save()
    
    def perform_destroy(self, instance):
        """Validate survey is editable"""
        if instance.survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot delete sections from published survey"
            )
        instance.delete()
    
    @extend_schema(
        summary="Bulk section operations",
        description="Perform bulk operations on sections: reorder or delete multiple sections",
        request=BulkOperationSerializer,
        tags=['Sections'],
        examples=[
            OpenApiExample(
                'Reorder sections',
                value={'operation': 'reorder', 'items': [{'id': 1, 'order': 2}, {'id': 2, 'order': 1}]},
            ),
            OpenApiExample(
                'Delete sections',
                value={'operation': 'delete', 'items': [1, 2, 3]},
            ),
        ]
    )
    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """
        Bulk operations on sections
        
        Supports: reorder, delete, duplicate
        """
        serializer = BulkOperationSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        operation = serializer.validated_data['operation']
        items = serializer.validated_data['items']
        
        if operation == 'reorder':
            with transaction.atomic():
                for item in items:
                    Section.objects.filter(id=item['id']).update(order=item['order'])
            
            return Response({
                'status': 'success',
                'message': f'{len(items)} sections reordered'
            })
        
        elif operation == 'delete':
            ids = [item['id'] for item in items]
            deleted = Section.objects.filter(id__in=ids).delete()
            
            return Response({
                'status': 'success',
                'message': f'{deleted[0]} sections deleted'
            })
        
        elif operation == 'duplicate':
            # TODO: Implement section duplication
            return Response({
                'status': 'error',
                'message': 'Duplicate operation not yet implemented'
            }, status=status.HTTP_501_NOT_IMPLEMENTED)
        
        return Response(
            {'status': 'error', 'message': 'Invalid operation'},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema_view(
    list=extend_schema(
        summary="List fields",
        description="Get all fields, optionally filtered by section or survey",
        parameters=[
            OpenApiParameter(name='section', description='Filter by section ID', type=OpenApiTypes.INT),
            OpenApiParameter(name='survey', description='Filter by survey ID', type=OpenApiTypes.INT),
        ],
        tags=['Fields'],
    ),
    create=extend_schema(
        summary="Create field",
        description="Create a new field in a section. Can include options for choice fields.",
        tags=['Fields'],
    ),
    retrieve=extend_schema(
        summary="Get field details",
        description="Get field details including options and validation rules",
        tags=['Fields'],
    ),
    update=extend_schema(
        summary="Update field",
        description="Update field properties",
        tags=['Fields'],
    ),
    destroy=extend_schema(
        summary="Delete field",
        description="Delete a field. Cannot delete if referenced in conditional logic.",
        tags=['Fields'],
    ),
)
class FieldViewSet(viewsets.ModelViewSet):
    """
    Field CRUD for survey builder
    
    Endpoints:
    - GET /fields/ - List fields (filtered by section/survey)
    - POST /fields/ - Create field
    - GET /fields/{id}/ - Get field detail
    - PATCH /fields/{id}/ - Update field
    - DELETE /fields/{id}/ - Delete field
    - POST /fields/bulk/ - Bulk operations (reorder, delete)
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter fields by section or survey"""
        queryset = Field.objects.select_related('section', 'section__survey').prefetch_related(
            'options', 'conditional_triggers', 'dependencies_to'
        )
        
        section_id = self.request.query_params.get('section_id')
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        
        survey_id = self.request.query_params.get('survey_id')
        if survey_id:
            queryset = queryset.filter(section__survey_id=survey_id)
        
        return queryset.order_by('section__order', 'order')
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action in ['create', 'update', 'partial_update']:
            # Check if nested data is provided
            if self.request.data.get('options'):
                return FieldSerializer
            return FieldCreateSerializer
        return FieldSerializer
    
    def perform_create(self, serializer):
        """Validate survey is editable"""
        section = serializer.validated_data['section']
        if section.survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot add fields to published survey"
            )
        serializer.save()
    
    def perform_update(self, serializer):
        """Validate survey is editable"""
        field = self.get_object()
        if field.section.survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot update fields in published survey"
            )
        serializer.save()
    
    def perform_destroy(self, instance):
        """Validate survey is editable and check dependencies"""
        if instance.section.survey.status == 'published':
            raise serializers.ValidationError(
                "Cannot delete fields from published survey"
            )
        
        # Check if field is referenced in conditional logic
        if ConditionalLogic.objects.filter(
            Q(trigger_field=instance) | Q(target_field=instance)
        ).exists():
            raise serializers.ValidationError(
                "Cannot delete field referenced in conditional logic"
            )
        
        # Check if field has dependencies
        if FieldDependency.objects.filter(
            Q(source_field=instance) | Q(dependent_field=instance)
        ).exists():
            raise serializers.ValidationError(
                "Cannot delete field with dependencies"
            )
        
        instance.delete()
    
    @extend_schema(
        summary="Bulk field operations",
        description="Perform bulk operations on fields: reorder or delete multiple fields",
        request=BulkOperationSerializer,
        tags=['Fields'],
    )
    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """Bulk operations on fields (reorder, delete, duplicate)"""
        serializer = BulkOperationSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        operation = serializer.validated_data['operation']
        items = serializer.validated_data['items']
        
        if operation == 'reorder':
            with transaction.atomic():
                for item in items:
                    Field.objects.filter(id=item['id']).update(order=item['order'])
            
            return Response({
                'status': 'success',
                'message': f'{len(items)} fields reordered'
            })
        
        elif operation == 'delete':
            ids = [item['id'] for item in items]
            deleted = Field.objects.filter(id__in=ids).delete()
            
            return Response({
                'status': 'success',
                'message': f'{deleted[0]} fields deleted'
            })
        
        return Response(
            {'status': 'error', 'message': 'Operation not supported'},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema_view(
    list=extend_schema(
        summary="List field options",
        description="Get all options for choice fields",
        parameters=[
            OpenApiParameter(name='field_id', description='Filter by field ID', type=OpenApiTypes.INT),
        ],
        tags=['Field Options'],
    ),
    create=extend_schema(
        summary="Create field option",
        description="Create a new option for a choice field",
        tags=['Field Options'],
    ),
    update=extend_schema(
        summary="Update field option",
        description="Update option label or value",
        tags=['Field Options'],
    ),
    destroy=extend_schema(
        summary="Delete field option",
        description="Delete an option from a field",
        tags=['Field Options'],
    ),
)
class FieldOptionViewSet(viewsets.ModelViewSet):
    """
    Field option CRUD
    
    Endpoints:
    - GET /field-options/ - List options (filtered by field)
    - POST /field-options/ - Create option
    - PATCH /field-options/{id}/ - Update option
    - DELETE /field-options/{id}/ - Delete option
    """
    
    serializer_class = FieldOptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter options by field"""
        queryset = FieldOption.objects.select_related('field')
        
        field_id = self.request.query_params.get('field_id')
        if field_id:
            queryset = queryset.filter(field_id=field_id)
        
        return queryset.order_by('order')


@extend_schema_view(
    list=extend_schema(
        summary="List conditional logic rules",
        description="Get all conditional logic rules for a survey",
        parameters=[
            OpenApiParameter(name='survey_id', description='Filter by survey ID', type=OpenApiTypes.INT),
        ],
        tags=['Conditional Logic'],
    ),
    create=extend_schema(
        summary="Create conditional logic",
        description="Create a new conditional logic rule to show/hide fields based on conditions",
        tags=['Conditional Logic'],
    ),
    retrieve=extend_schema(
        summary="Get logic details",
        description="Get conditional logic rule details",
        tags=['Conditional Logic'],
    ),
    update=extend_schema(
        summary="Update logic rule",
        description="Update conditional logic conditions",
        tags=['Conditional Logic'],
    ),
    destroy=extend_schema(
        summary="Delete logic rule",
        description="Delete a conditional logic rule",
        tags=['Conditional Logic'],
    ),
)
class ConditionalLogicViewSet(viewsets.ModelViewSet):
    """
    Conditional logic CRUD
    
    Endpoints:
    - GET /conditional-logic/ - List logic rules (filtered by survey)
    - POST /conditional-logic/ - Create logic rule
    - GET /conditional-logic/{id}/ - Get logic detail
    - PATCH /conditional-logic/{id}/ - Update logic
    - DELETE /conditional-logic/{id}/ - Delete logic
    """
    
    serializer_class = ConditionalLogicSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter logic by survey"""
        queryset = ConditionalLogic.objects.select_related(
            'trigger_field', 'target_field', 'target_section'
        )
        
        survey_id = self.request.query_params.get('survey_id')
        if survey_id:
            queryset = queryset.filter(trigger_field__section__survey_id=survey_id)
        
        return queryset.order_by('priority')


@extend_schema_view(
    list=extend_schema(
        summary="List field dependencies",
        description="Get all field dependencies for a survey",
        parameters=[
            OpenApiParameter(name='survey_id', description='Filter by survey ID', type=OpenApiTypes.INT),
        ],
        tags=['Field Dependencies'],
    ),
    create=extend_schema(
        summary="Create field dependency",
        description="Create a dependency relationship between two fields",
        tags=['Field Dependencies'],
    ),
    destroy=extend_schema(
        summary="Delete field dependency",
        description="Remove a dependency relationship",
        tags=['Field Dependencies'],
    ),
)
class FieldDependencyViewSet(viewsets.ModelViewSet):
    """
    Field dependency CRUD
    
    Endpoints:
    - GET /field-dependencies/ - List dependencies (filtered by survey)
    - POST /field-dependencies/ - Create dependency
    - DELETE /field-dependencies/{id}/ - Delete dependency
    """
    
    serializer_class = FieldDependencySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter dependencies by survey"""
        queryset = FieldDependency.objects.select_related(
            'source_field', 'dependent_field'
        )
        
        survey_id = self.request.query_params.get('survey_id')
        if survey_id:
            queryset = queryset.filter(source_field__section__survey_id=survey_id)
        
        return queryset
