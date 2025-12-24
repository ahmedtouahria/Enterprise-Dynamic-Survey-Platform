"""
Survey API Serializers

Nested serializers for survey builder with validation.
Designed for step-by-step survey creation like Typeform/SurveyMonkey.
"""

from rest_framework import serializers
from django.db import transaction
from django.db import models
from .models import (
    Survey, Section, Field, FieldOption,
    ConditionalLogic, FieldDependency
)



class FieldOptionSerializer(serializers.ModelSerializer):
    """Serializer for field options (choice fields)"""
    
    class Meta:
        model = FieldOption
        fields = [
            'id', 'label', 'value', 'order', 'is_exclusive',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_order(self, value):
        """Ensure order is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Order must be non-negative")
        return value


class ConditionalLogicSerializer(serializers.ModelSerializer):
    """Serializer for conditional logic rules"""
    
    trigger_field_label = serializers.CharField(source='trigger_field.label', read_only=True)
    target_field_label = serializers.CharField(source='target_field.label', read_only=True)
    target_section_title = serializers.CharField(source='target_section.title', read_only=True)
    
    class Meta:
        model = ConditionalLogic
        fields = [
            'id', 'trigger_field', 'trigger_field_label',
            'target_field', 'target_field_label',
            'target_section', 'target_section_title',
            'action', 'condition', 'priority',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_condition(self, value):
        """
        Validate conditional logic JSON structure.
        
        Required structure:
        {
            "operator": "AND" | "OR",
            "conditions": [
                {
                    "field_id": int,
                    "operator": "equals" | "not_equals" | "contains" | "greater_than" | "less_than" | "is_empty" | "is_not_empty",
                    "value": any
                }
            ]
        }
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("Condition must be a JSON object")
        
        if 'operator' not in value:
            raise serializers.ValidationError("Condition must have 'operator' field")
        
        if value['operator'] not in ['AND', 'OR']:
            raise serializers.ValidationError("Operator must be 'AND' or 'OR'")
        
        if 'conditions' not in value or not isinstance(value['conditions'], list):
            raise serializers.ValidationError("Condition must have 'conditions' array")
        
        allowed_operators = [
            'equals', 'not_equals', 'contains', 'greater_than',
            'less_than', 'is_empty', 'is_not_empty'
        ]
        
        for cond in value['conditions']:
            if not isinstance(cond, dict):
                raise serializers.ValidationError("Each condition must be an object")
            
            if 'field_id' not in cond:
                raise serializers.ValidationError("Each condition must have 'field_id'")
            
            if 'operator' not in cond:
                raise serializers.ValidationError("Each condition must have 'operator'")
            
            if cond['operator'] not in allowed_operators:
                raise serializers.ValidationError(
                    f"Condition operator must be one of: {', '.join(allowed_operators)}"
                )
            
            # Value is optional for is_empty/is_not_empty
            if cond['operator'] not in ['is_empty', 'is_not_empty'] and 'value' not in cond:
                raise serializers.ValidationError(
                    f"Condition with operator '{cond['operator']}' must have 'value'"
                )
        
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Must have either target_field or target_section
        if not data.get('target_field') and not data.get('target_section'):
            raise serializers.ValidationError(
                "Must specify either target_field or target_section"
            )
        
        # Cannot have both
        if data.get('target_field') and data.get('target_section'):
            raise serializers.ValidationError(
                "Cannot specify both target_field and target_section"
            )
        
        return data


class FieldDependencySerializer(serializers.ModelSerializer):
    """Serializer for field dependencies"""
    
    source_field_label = serializers.CharField(source='source_field.label', read_only=True)
    dependent_field_label = serializers.CharField(source='dependent_field.label', read_only=True)
    
    class Meta:
        model = FieldDependency
        fields = [
            'id', 'source_field', 'source_field_label',
            'dependent_field', 'dependent_field_label',
            'dependency_type',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Prevent circular dependencies"""
        source = data.get('source_field')
        dependent = data.get('dependent_field')
        
        if source == dependent:
            raise serializers.ValidationError(
                "A field cannot depend on itself"
            )
        
        # Check for circular dependency
        # TODO: Implement graph traversal to detect cycles
        
        return data


class FieldSerializer(serializers.ModelSerializer):
    """Serializer for survey fields with nested options and logic"""
    
    options = FieldOptionSerializer(many=True, required=False)
    conditional_triggers = ConditionalLogicSerializer(many=True, read_only=True)
    dependencies_to = FieldDependencySerializer(many=True, read_only=True)
    
    class Meta:
        model = Field
        fields = [
            'id', 'label', 'field_type', 'description', 'placeholder',
            'order', 'is_required', 'is_conditional', 'is_encrypted',
            'min_value', 'max_value', 'min_length', 'max_length',
            'regex_pattern', 'config', 'options',
            'conditional_triggers', 'dependencies_to',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_field_type(self, value):
        """Ensure valid field type"""
        valid_types = [choice[0] for choice in Field.FIELD_TYPES]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Invalid field type. Must be one of: {', '.join(valid_types)}"
            )
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        field_type = data.get('field_type')
        options = self.initial_data.get('options', [])
        
        # Choice fields must have options
        choice_types = ['single_choice', 'multiple_choice', 'dropdown']
        if field_type in choice_types and not options:
            raise serializers.ValidationError(
                f"Field type '{field_type}' requires at least one option"
            )
        
        # Non-choice fields should not have options
        if field_type not in choice_types and options:
            raise serializers.ValidationError(
                f"Field type '{field_type}' cannot have options"
            )
        
        # Validate min/max ranges
        if data.get('min_value') is not None and data.get('max_value') is not None:
            if data['min_value'] > data['max_value']:
                raise serializers.ValidationError(
                    "min_value must be less than or equal to max_value"
                )
        
        if data.get('min_length') is not None and data.get('max_length') is not None:
            if data['min_length'] > data['max_length']:
                raise serializers.ValidationError(
                    "min_length must be less than or equal to max_length"
                )
        
        return data
    
    def create(self, validated_data):
        """Create field with nested options"""
        options_data = validated_data.pop('options', [])
        field = Field.objects.create(**validated_data)
        
        # Create options
        for option_data in options_data:
            FieldOption.objects.create(field=field, **option_data)
        
        return field
    
    def update(self, instance, validated_data):
        """Update field and manage options"""
        options_data = validated_data.pop('options', None)
        
        # Update field
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update options if provided
        if options_data is not None:
            # Delete existing options
            instance.options.all().delete()
            
            # Create new options
            for option_data in options_data:
                FieldOption.objects.create(field=instance, **option_data)
        
        return instance


class FieldCreateSerializer(serializers.ModelSerializer):
    """Lightweight serializer for creating fields without nested data"""
    
    class Meta:
        model = Field
        fields = [
            'id', 'section', 'label', 'field_type', 'description',
            'placeholder', 'order', 'is_required', 'is_conditional',
            'is_encrypted', 'min_value', 'max_value', 'min_length',
            'max_length', 'regex_pattern', 'config'
        ]
        read_only_fields = ['id']


class SectionSerializer(serializers.ModelSerializer):
    """Serializer for survey sections with nested fields"""
    
    fields = FieldSerializer(many=True, read_only=True)
    field_count = serializers.IntegerField(source='fields.count', read_only=True)
    
    class Meta:
        model = Section
        fields = [
            'id', 'title', 'description', 'order', 'is_conditional',
            'fields', 'field_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_order(self, value):
        """Ensure order is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Order must be non-negative")
        return value


class SectionCreateSerializer(serializers.ModelSerializer):
    """Lightweight serializer for creating sections"""
    
    class Meta:
        model = Section
        fields = ['id', 'survey', 'title', 'description', 'order', 'is_conditional']
        read_only_fields = ['id']


class SurveyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for survey list view"""
    
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        default='Unknown'
    )
    section_count = serializers.IntegerField(source='sections.count', read_only=True)
    response_count = serializers.IntegerField(source='responses.count', read_only=True)
    
    class Meta:
        model = Survey
        fields = [
            'id', 'title', 'description', 'status', 'version',
            'is_active_version', 'created_by_name', 'section_count',
            'response_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'version', 'created_at', 'updated_at']


class SurveyDetailSerializer(serializers.ModelSerializer):
    """Full serializer for survey detail view with nested sections and fields"""
    
    sections = SectionSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        default='Unknown'
    )
    versions = serializers.SerializerMethodField()
    
    class Meta:
        model = Survey
        fields = [
            'id', 'title', 'description', 'status', 'version',
            'parent_survey', 'is_active_version', 'created_by',
            'created_by_name', 'tenant_id', 'allow_multiple_submissions',
            'allow_partial_submissions', 'submission_deadline',
            'metadata', 'sections', 'versions',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'version', 'parent_survey', 'created_by',
            'created_at', 'updated_at'
        ]
    
    def get_versions(self, obj):
        """Get all versions of this survey"""
        if obj.parent_survey:
            root = obj.parent_survey
        else:
            root = obj
        
        versions = Survey.objects.filter(
            models.Q(id=root.id) | models.Q(parent_survey=root)
        ).order_by('-version').values('id', 'version', 'status', 'is_active_version', 'created_at')
        
        return list(versions)


class SurveyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating surveys"""
    
    class Meta:
        model = Survey
        fields = [
            'id', 'title', 'description', 'status', 'tenant_id',
            'allow_multiple_submissions', 'allow_partial_submissions',
            'submission_deadline', 'metadata'
        ]
        read_only_fields = ['id']
    
    def validate_status(self, value):
        """Only allow draft status on creation"""
        if value != 'draft':
            raise serializers.ValidationError(
                "New surveys must start as 'draft'"
            )
        return value
    
    def create(self, validated_data):
        """Create survey with current user as creator"""
        validated_data['created_by'] = self.context['request'].user
        validated_data['version'] = 1
        validated_data['is_active_version'] = True
        return super().create(validated_data)


class SurveyUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating survey metadata"""
    
    class Meta:
        model = Survey
        fields = [
            'title', 'description', 'allow_multiple_submissions',
            'allow_partial_submissions', 'submission_deadline', 'metadata'
        ]
    
    def validate(self, data):
        """Prevent updates to published surveys"""
        if self.instance.status == 'published':
            raise serializers.ValidationError(
                "Cannot update published surveys. Create a new version instead."
            )
        return data


class SurveyPublishSerializer(serializers.Serializer):
    """Serializer for publishing surveys"""
    
    def validate(self, data):
        """Validate survey is ready to publish"""
        survey = self.instance
        
        # Must have at least one section
        if not survey.sections.exists():
            raise serializers.ValidationError(
                "Survey must have at least one section before publishing"
            )
        
        # All sections must have at least one field
        for section in survey.sections.all():
            if not section.fields.exists():
                raise serializers.ValidationError(
                    f"Section '{section.title}' must have at least one field"
                )
        
        # Validate all conditional logic references valid fields
        for logic in ConditionalLogic.objects.filter(
            trigger_field__section__survey=survey
        ):
            # Check if referenced fields exist in condition
            condition = logic.condition
            if 'conditions' in condition:
                for cond in condition['conditions']:
                    field_id = cond.get('field_id')
                    if field_id and not Field.objects.filter(
                        id=field_id,
                        section__survey=survey
                    ).exists():
                        raise serializers.ValidationError(
                            f"Conditional logic references non-existent field ID: {field_id}"
                        )
        
        return data


class SurveyVersionSerializer(serializers.Serializer):
    """Serializer for creating new survey version"""
    
    copy_structure = serializers.BooleanField(
        default=True,
        help_text="Copy sections, fields, and options to new version"
    )
    
    def validate(self, data):
        """Validate survey can be versioned"""
        survey = self.instance
        
        if survey.status != 'published':
            raise serializers.ValidationError(
                "Only published surveys can be versioned"
            )
        
        return data


class BulkOperationSerializer(serializers.Serializer):
    """Serializer for bulk operations (reorder, delete, etc.)"""
    
    operation = serializers.ChoiceField(
        choices=['reorder', 'delete', 'duplicate'],
        help_text="Type of bulk operation"
    )
    items = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of items with their IDs and new values"
    )
    
    def validate_items(self, value):
        """Validate items structure based on operation"""
        operation = self.initial_data.get('operation')
        
        if operation == 'reorder':
            for item in value:
                if 'id' not in item or 'order' not in item:
                    raise serializers.ValidationError(
                        "Each item must have 'id' and 'order' for reorder operation"
                    )
        
        elif operation == 'delete':
            for item in value:
                if 'id' not in item:
                    raise serializers.ValidationError(
                        "Each item must have 'id' for delete operation"
                    )
        
        elif operation == 'duplicate':
            for item in value:
                if 'id' not in item:
                    raise serializers.ValidationError(
                        "Each item must have 'id' for duplicate operation"
                    )
        
        return value
