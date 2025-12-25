"""
Survey Models

Core models for survey structure with versioning support.
Surveys are versioned to allow editing without breaking existing responses.
"""

from django.db import models



class TimeStampedModel(models.Model):
    """Abstract base model with timestamp fields"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Survey(TimeStampedModel):
    """
    Main survey definition with versioning support.
    
    Versioning Strategy:
    - When a survey is published, its version is incremented
    - Old versions remain immutable (is_active=False)
    - New responses always reference the latest active version
    - Historical responses remain linked to their original version
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    # Basic fields
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    
    # Versioning
    version = models.PositiveIntegerField(default=1)
    parent_survey = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions',
        help_text='Reference to original survey for version tracking'
    )
    is_active_version = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Only one version should be active at a time'
    )
    
    # Ownership & multi-tenancy
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='surveys_created'
    )
    tenant_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='For multi-tenant isolation'
    )
    
    # Settings
    allow_multiple_submissions = models.BooleanField(default=False)
    allow_partial_submissions = models.BooleanField(default=True)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional survey configuration'
    )
    
    class Meta:
        db_table = 'surveys'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'status', 'is_active_version']),
            models.Index(fields=['parent_survey', 'version']),
            models.Index(fields=['created_by', 'status']),
        ]
        # Ensure only one active version per survey lineage
        constraints = [
            models.UniqueConstraint(
                fields=['parent_survey', 'is_active_version'],
                condition=models.Q(is_active_version=True),
                name='unique_active_version_per_survey'
            )
        ]
    
    def __str__(self):
        return f"{self.title} (v{self.version})"
    
    def create_new_version(self):
        """
        Creates a new version of this survey.
        Returns the new survey instance.
        """
        # Deactivate current version
        self.is_active_version = False
        self.save(update_fields=['is_active_version'])
        
        # Create new version
        new_survey = Survey.objects.create(
            title=self.title,
            description=self.description,
            status='draft',
            version=self.version + 1,
            parent_survey=self.parent_survey or self,
            is_active_version=True,
            created_by=self.created_by,
            tenant_id=self.tenant_id,
            allow_multiple_submissions=self.allow_multiple_submissions,
            allow_partial_submissions=self.allow_partial_submissions,
            metadata=self.metadata.copy(),
        )
        
        return new_survey


class Section(TimeStampedModel):
    """
    Survey sections for grouping fields.
    Sections belong to a specific survey version.
    """
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    
    # Conditional display
    is_conditional = models.BooleanField(
        default=False,
        help_text='Whether this section visibility depends on other field values'
    )
    
    class Meta:
        db_table = 'survey_sections'
        ordering = ['survey', 'order']
        indexes = [
            models.Index(fields=['survey', 'order']),
        ]
    
    def __str__(self):
        return f"{self.survey.title} - {self.title}"


class Field(TimeStampedModel):
    """
    Survey fields with support for various types and validation.
    Fields are versioned as part of survey versions.
    """
    
    FIELD_TYPES = [
        ('text', 'Text'),
        ('textarea', 'Text Area'),
        ('number', 'Number'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('date', 'Date'),
        ('datetime', 'Date & Time'),
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('dropdown', 'Dropdown'),
        ('file_upload', 'File Upload'),
        ('rating', 'Rating'),
        ('slider', 'Slider'),
        ('matrix', 'Matrix'),
        ('boolean', 'Yes/No'),
    ]
    
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='fields'
    )
    
    # Field definition
    label = models.CharField(max_length=500)
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES, db_index=True)
    description = models.TextField(blank=True)
    placeholder = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    # Validation
    is_required = models.BooleanField(default=False)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    min_length = models.PositiveIntegerField(null=True, blank=True)
    max_length = models.PositiveIntegerField(null=True, blank=True)
    regex_pattern = models.CharField(max_length=500, blank=True)
    
    # Conditional logic
    is_conditional = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether this field visibility depends on other field values'
    )
    
    # Encryption support for sensitive fields
    is_encrypted = models.BooleanField(
        default=False,
        help_text='Encrypt responses to this field at rest'
    )
    
    # Additional configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional field configuration (e.g., min/max for rating, step for slider)'
    )
    
    class Meta:
        db_table = 'survey_fields'
        ordering = ['section', 'order']
        indexes = [
            models.Index(fields=['section', 'order']),
            models.Index(fields=['field_type', 'is_conditional']),
        ]
    
    def __str__(self):
        return f"{self.section.title} - {self.label}"


class FieldOption(TimeStampedModel):
    """
    Options for choice-based fields (single_choice, multiple_choice, dropdown).
    """
    field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name='options'
    )
    label = models.CharField(max_length=500)
    value = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    
    # Conditional branching
    is_exclusive = models.BooleanField(
        default=False,
        help_text='For multiple choice: selecting this clears other options'
    )
    
    class Meta:
        db_table = 'field_options'
        ordering = ['field', 'order']
        indexes = [
            models.Index(fields=['field', 'order']),
        ]
    
    def __str__(self):
        return f"{self.field.label} - {self.label}"


class ConditionalLogic(TimeStampedModel):
    """
    Defines conditional display/skip logic between fields.
    
    Logic evaluation happens at runtime when displaying surveys or validating responses.
    Uses JSON to store complex conditional expressions for flexibility.
    
    Example condition structure:
    {
        "operator": "AND",
        "conditions": [
            {"field_id": 123, "operator": "equals", "value": "yes"},
            {"field_id": 124, "operator": "greater_than", "value": 18}
        ]
    }
    """
    
    ACTION_TYPES = [
        ('show', 'Show Field/Section'),
        ('hide', 'Hide Field/Section'),
        ('require', 'Make Required'),
        ('skip_to', 'Skip to Section'),
    ]
    
    # What triggers this logic
    trigger_field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name='conditional_triggers',
        help_text='Field whose value triggers this logic'
    )
    
    # What is affected
    target_field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name='conditional_targets',
        null=True,
        blank=True,
        help_text='Field affected by this logic'
    )
    target_section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='conditional_targets',
        null=True,
        blank=True,
        help_text='Section affected by this logic'
    )
    
    # Logic definition
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    condition = models.JSONField(
        help_text='Conditional expression in JSON format'
    )
    
    # Priority for multiple conflicting rules
    priority = models.PositiveIntegerField(
        default=0,
        help_text='Higher priority rules execute first'
    )
    
    class Meta:
        db_table = 'conditional_logic'
        ordering = ['-priority', 'id']
        indexes = [
            models.Index(fields=['trigger_field', 'priority']),
            models.Index(fields=['target_field']),
            models.Index(fields=['target_section']),
        ]
        # Use GIN index for JSON field queries (PostgreSQL specific)
        # Run: CREATE INDEX conditional_logic_condition_gin ON conditional_logic USING GIN (condition);
    
    def __str__(self):
        target = self.target_field or self.target_section
        return f"If {self.trigger_field.label} then {self.action} {target}"
    
    def evaluate(self, response_data):
        """
        Evaluate if this conditional logic should trigger based on response data.
        
        Args:
            response_data: dict of field_id -> value
        
        Returns:
            bool: True if condition is met
        """
        condition = self.condition
        
        # Simple evaluation (can be extended)
        if 'operator' in condition:
            operator = condition['operator']
            conditions = condition.get('conditions', [])
            
            results = []
            for cond in conditions:
                field_id = cond.get('field_id')
                op = cond.get('operator')
                expected_value = cond.get('value')
                actual_value = response_data.get(field_id)
                
                if op == 'equals':
                    results.append(actual_value == expected_value)
                elif op == 'not_equals':
                    results.append(actual_value != expected_value)
                elif op == 'contains':
                    results.append(expected_value in (actual_value or ''))
                elif op == 'greater_than':
                    results.append(float(actual_value or 0) > float(expected_value))
                elif op == 'less_than':
                    results.append(float(actual_value or 0) < float(expected_value))
                elif op == 'is_empty':
                    results.append(not actual_value)
                elif op == 'is_not_empty':
                    results.append(bool(actual_value))
            
            if operator == 'AND':
                return all(results)
            elif operator == 'OR':
                return any(results)
            else:
                return False
        
        return False


class FieldDependency(TimeStampedModel):
    """
    Tracks dependencies between fields for validation and display order.
    Helps with optimizing conditional logic evaluation.
    """
    source_field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name='dependencies_from',
        help_text='Field that is depended upon'
    )
    dependent_field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name='dependencies_to',
        help_text='Field that depends on source_field'
    )
    
    dependency_type = models.CharField(
        max_length=50,
        choices=[
            ('conditional_display', 'Conditional Display'),
            ('conditional_validation', 'Conditional Validation'),
            ('calculated_value', 'Calculated Value'),
        ]
    )
    
    class Meta:
        db_table = 'field_dependencies'
        unique_together = ['source_field', 'dependent_field', 'dependency_type']
        indexes = [
            models.Index(fields=['source_field', 'dependency_type']),
            models.Index(fields=['dependent_field']),
        ]
    
    def __str__(self):
        return f"{self.dependent_field.label} depends on {self.source_field.label}"
