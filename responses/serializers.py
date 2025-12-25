"""
Response Submission Serializers

Handles validation and serialization for survey responses, partial submissions,
and incremental answer updates.
"""

from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import SurveyResponse, SurveyResponseItem, PartialResponse
from surveys.models import Survey, Field, ConditionalLogic
from surveys.logic_engine import LogicEngine


class ResponseItemSerializer(serializers.Serializer):
    """Serializer for individual field responses."""
    
    field_id = serializers.IntegerField()
    value = serializers.JSONField()
    
    def validate_field_id(self, value):
        """Ensure field exists."""
        if not Field.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Field with id {value} does not exist")
        return value


class PartialResponseSerializer(serializers.ModelSerializer):
    """Serializer for partial (in-progress) responses."""
    
    responses = serializers.JSONField()
    resume_token = serializers.CharField(read_only=True)
    
    class Meta:
        model = PartialResponse
        fields = [
            'id', 'survey', 'session_id', 'responses', 
            'resume_token', 'created_at', 'updated_at', 'expires_at'
        ]
        read_only_fields = ['id', 'resume_token', 'created_at', 'updated_at']
    
    def validate_responses(self, value):
        """Validate responses structure."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Responses must be a dictionary")
        
        # Validate each field_id is a string or int
        for field_id in value.keys():
            if not isinstance(field_id, (str, int)):
                raise serializers.ValidationError(f"Invalid field_id: {field_id}")
        
        return value
    
    def create(self, validated_data):
        """Create partial response with generated token."""
        import secrets
        validated_data['resume_token'] = secrets.token_urlsafe(32)
        return super().create(validated_data)


class IncrementalSubmissionSerializer(serializers.Serializer):
    """
    Serializer for incremental (step-by-step) response submission.
    
    Accepts one or more field responses and validates them against
    the survey structure and conditional logic.
    """
    
    survey_id = serializers.IntegerField()
    session_id = serializers.CharField(required=False, allow_null=True)
    resume_token = serializers.CharField(required=False, allow_null=True)
    responses = serializers.ListField(
        child=ResponseItemSerializer(),
        allow_empty=False
    )
    
    def validate_survey_id(self, value):
        """Ensure survey exists and is published."""
        try:
            survey = Survey.objects.get(id=value)
        except Survey.DoesNotExist:
            raise serializers.ValidationError(f"Survey with id {value} does not exist")
        
        if survey.status != 'published':
            raise serializers.ValidationError("Survey is not published")
        
        return value
    
    def validate(self, data):
        """Validate responses against survey structure and logic."""
        survey_id = data['survey_id']
        responses = data['responses']
        
        # Get survey with all fields
        survey = Survey.objects.prefetch_related(
            'sections__fields__options',
            'sections__fields__target_conditional_logic'
        ).get(id=survey_id)
        
        # Validate each response
        field_ids = [r['field_id'] for r in responses]
        fields = Field.objects.filter(
            id__in=field_ids,
            section__survey=survey
        ).select_related('section')
        
        field_map = {f.id: f for f in fields}
        
        for response in responses:
            field_id = response['field_id']
            value = response['value']
            
            if field_id not in field_map:
                raise serializers.ValidationError(
                    f"Field {field_id} does not belong to survey {survey_id}"
                )
            
            field = field_map[field_id]
            
            # Validate field value based on field type
            try:
                self._validate_field_value(field, value)
            except DjangoValidationError as e:
                raise serializers.ValidationError(
                    {f'field_{field_id}': str(e)}
                )
        
        return data
    
    def _validate_field_value(self, field, value):
        """Validate value based on field type."""
        
        # Empty value check
        if field.is_required and (value is None or value == ''):
            raise DjangoValidationError("This field is required")
        
        # Allow empty for non-required fields
        if value is None or value == '':
            return
        
        # Type-specific validation
        if field.field_type == 'email':
            self._validate_email(value)
        
        elif field.field_type == 'number':
            self._validate_number(field, value)
        
        elif field.field_type in ['single_choice', 'multiple_choice', 'dropdown']:
            self._validate_choice(field, value)
        
        elif field.field_type == 'phone':
            self._validate_phone(value)
        
        elif field.field_type == 'url':
            self._validate_url(value)
        
        elif field.field_type in ['text', 'textarea']:
            self._validate_text(field, value)
        
        elif field.field_type == 'date':
            self._validate_date(value)
        
        elif field.field_type == 'time':
            self._validate_time(value)
        
        elif field.field_type == 'datetime':
            self._validate_datetime(value)
    
    def _validate_email(self, value):
        """Validate email format."""
        from django.core.validators import validate_email
        try:
            validate_email(value)
        except DjangoValidationError:
            raise DjangoValidationError("Invalid email format")
    
    def _validate_number(self, field, value):
        """Validate numeric value and range."""
        try:
            num_value = float(value)
        except (TypeError, ValueError):
            raise DjangoValidationError("Value must be a number")
        
        if field.min_value is not None and num_value < field.min_value:
            raise DjangoValidationError(f"Value must be at least {field.min_value}")
        
        if field.max_value is not None and num_value > field.max_value:
            raise DjangoValidationError(f"Value must be at most {field.max_value}")
    
    def _validate_choice(self, field, value):
        """Validate choice field value against options."""
        valid_values = list(field.options.values_list('value', flat=True))
        
        if field.field_type == 'multiple_choice':
            if not isinstance(value, list):
                raise DjangoValidationError("Multiple choice requires a list of values")
            
            for v in value:
                if v not in valid_values:
                    raise DjangoValidationError(f"Invalid choice: {v}")
        else:
            if value not in valid_values:
                raise DjangoValidationError(f"Invalid choice: {value}")
    
    def _validate_phone(self, value):
        """Validate phone number format."""
        import re
        # Simple phone validation (can be customized)
        if not re.match(r'^\+?[\d\s\-\(\)]+$', str(value)):
            raise DjangoValidationError("Invalid phone number format")
    
    def _validate_url(self, value):
        """Validate URL format."""
        from django.core.validators import URLValidator
        validator = URLValidator()
        try:
            validator(value)
        except DjangoValidationError:
            raise DjangoValidationError("Invalid URL format")
    
    def _validate_text(self, field, value):
        """Validate text length."""
        text_length = len(str(value))
        
        if field.min_value is not None and text_length < field.min_value:
            raise DjangoValidationError(
                f"Text must be at least {field.min_value} characters"
            )
        
        if field.max_value is not None and text_length > field.max_value:
            raise DjangoValidationError(
                f"Text must be at most {field.max_value} characters"
            )
    
    def _validate_date(self, value):
        """Validate date format."""
        from datetime import datetime
        try:
            datetime.fromisoformat(str(value))
        except ValueError:
            raise DjangoValidationError("Invalid date format (use ISO format)")
    
    def _validate_time(self, value):
        """Validate time format."""
        from datetime import datetime
        try:
            datetime.strptime(str(value), '%H:%M:%S')
        except ValueError:
            try:
                datetime.strptime(str(value), '%H:%M')
            except ValueError:
                raise DjangoValidationError("Invalid time format (use HH:MM:SS or HH:MM)")
    
    def _validate_datetime(self, value):
        """Validate datetime format."""
        from datetime import datetime
        try:
            datetime.fromisoformat(str(value))
        except ValueError:
            raise DjangoValidationError("Invalid datetime format (use ISO format)")


class FinalSubmissionSerializer(serializers.Serializer):
    """
    Serializer for final (complete) survey submission.
    
    Validates all required fields are present and creates immutable response.
    """
    
    survey_id = serializers.IntegerField()
    session_id = serializers.CharField(required=False, allow_null=True)
    resume_token = serializers.CharField(required=False, allow_null=True)
    responses = serializers.ListField(
        child=ResponseItemSerializer(),
        allow_empty=False
    )
    user_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate(self, data):
        """Validate complete submission."""
        survey_id = data['survey_id']
        responses = data['responses']
        
        # Get survey with all required fields
        survey = Survey.objects.prefetch_related(
            'sections__fields__options'
        ).get(id=survey_id)
        
        # Build response map
        response_map = {r['field_id']: r['value'] for r in responses}
        
        # Evaluate conditional logic to determine visible fields
        visible_fields = self._evaluate_conditional_logic(survey, response_map)
        
        # Get all required fields
        required_fields = Field.objects.filter(
            section__survey=survey,
            is_required=True,
            id__in=visible_fields  # Only check visible required fields
        )
        
        # Check all required fields are present
        missing_fields = []
        for field in required_fields:
            if field.id not in response_map or response_map[field.id] in (None, ''):
                missing_fields.append(field.id)
        
        if missing_fields:
            raise serializers.ValidationError({
                'missing_fields': f"Required fields missing: {missing_fields}"
            })
        
        # Validate using incremental validator
        incremental_validator = IncrementalSubmissionSerializer(data=data)
        incremental_validator.is_valid(raise_exception=True)
        
        return data
    
    def _evaluate_conditional_logic(self, survey, response_map):
        """
        Evaluate conditional logic to determine which fields should be visible.
        
        Returns set of visible field IDs.
        """
        # Get all conditional logic for this survey
        logic_rules = ConditionalLogic.objects.filter(
            trigger_field__section__survey=survey
        ).select_related('trigger_field', 'target_field')
        
        # Initialize logic engine
        engine = LogicEngine(response_map)
        
        # All fields are visible by default
        all_field_ids = set(
            Field.objects.filter(section__survey=survey).values_list('id', flat=True)
        )
        visible_fields = all_field_ids.copy()
        
        # Evaluate each logic rule
        for rule in logic_rules:
            try:
                result = engine.evaluate(rule.condition)
                
                # Update visibility based on action
                if rule.action == 'show' and result:
                    visible_fields.add(rule.target_field.id)
                elif rule.action == 'hide' and result:
                    visible_fields.discard(rule.target_field.id)
                elif rule.action == 'show' and not result:
                    visible_fields.discard(rule.target_field.id)
                    
            except Exception as e:
                # Log error but continue (default to visible)
                pass
        
        return visible_fields


class ResponseRetrievalSerializer(serializers.ModelSerializer):
    """Serializer for retrieving existing responses."""
    
    items = serializers.SerializerMethodField()
    
    class Meta:
        model = SurveyResponse
        fields = [
            'id', 'survey', 'user', 'session_id', 'is_complete',
            'start_time', 'completion_time', 'items', 'created_at'
        ]
    
    def get_items(self, obj):
        """Get all response items."""
        items = obj.items.select_related('field').all()
        return [
            {
                'field_id': item.field.id,
                'field_label': item.field.label,
                'value': item.value
            }
            for item in items
        ]


class ResponseValidationSerializer(serializers.Serializer):
    """Serializer for validating responses without saving."""
    
    survey_id = serializers.IntegerField()
    responses = serializers.ListField(
        child=ResponseItemSerializer(),
        allow_empty=False
    )
    
    def validate(self, data):
        """Validate responses."""
        # Use incremental validator
        validator = IncrementalSubmissionSerializer(data=data)
        validator.is_valid(raise_exception=True)
        return data
