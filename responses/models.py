"""
Response Models

Models for handling survey responses with support for:
- Complete and partial submissions
- Resume functionality
- Immutable responses (audit trail)
- Encryption for sensitive data
"""

from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
from django.utils import timezone
import json
import base64


class TimeStampedModel(models.Model):
    """Abstract base model with timestamp fields"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SurveyResponse(TimeStampedModel):
    """
    Main response entity. Immutable once submitted.
    Partitioned by created_at for performance on large datasets.
    """
    
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    # Survey reference (locked to specific version)
    survey = models.ForeignKey(
        'surveys.Survey',
        on_delete=models.PROTECT,  # Never delete surveys with responses
        related_name='responses'
    )
    
    # Respondent info
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='survey_responses',
        help_text='Authenticated user (optional for anonymous surveys)'
    )
    respondent_email = models.EmailField(
        blank=True,
        db_index=True,
        help_text='For anonymous responses'
    )
    
    # Response metadata
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        db_index=True
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='When response was finalized'
    )
    
    # Resume support
    resume_token = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='Token for resuming partial submissions'
    )
    
    # Multi-tenancy
    tenant_id = models.CharField(
        max_length=100,
        db_index=True
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional response metadata (device info, referrer, etc.)'
    )
    
    class Meta:
        db_table = 'survey_responses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['survey', 'status', 'created_at']),
            models.Index(fields=['user', 'survey']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['submitted_at']),
            # For time-series queries
            models.Index(fields=['created_at', 'survey']),
        ]
        # Partitioning (requires PostgreSQL 10+)
        # Run: CREATE TABLE survey_responses_y2025m01 PARTITION OF survey_responses
        #      FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    
    def __str__(self):
        return f"Response {self.id} to {self.survey.title}"
    
    def mark_completed(self):
        """Mark response as completed and set submission timestamp"""
        if self.status != 'completed':
            self.status = 'completed'
            self.submitted_at = timezone.now()
            self.save(update_fields=['status', 'submitted_at'])
    
    def is_editable(self):
        """Check if response can still be edited"""
        return self.status == 'in_progress'


class SurveyResponseItem(TimeStampedModel):
    """
    Individual field responses. Immutable once parent response is submitted.
    Supports encryption for sensitive fields.
    
    Performance Optimization:
    - Partitioned by created_at monthly
    - Indexed on response + field for quick lookups
    - Encrypted values stored as base64 strings
    """
    
    response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='items'
    )
    field = models.ForeignKey(
        'surveys.Field',
        on_delete=models.PROTECT,
        related_name='responses'
    )
    
    # Value storage (supports multiple types)
    value_text = models.TextField(blank=True)
    value_number = models.FloatField(null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_json = models.JSONField(
        null=True,
        blank=True,
        help_text='For complex values like multiple choice, matrix, etc.'
    )
    
    # Encryption support
    is_encrypted = models.BooleanField(
        default=False,
        help_text='Whether value_text is encrypted'
    )
    
    # File uploads
    file_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text='S3/cloud storage URL for file uploads'
    )
    
    class Meta:
        db_table = 'survey_response_items'
        ordering = ['response', 'field']
        indexes = [
            models.Index(fields=['response', 'field']),
            models.Index(fields=['field', 'created_at']),
            # For analytics queries
            models.Index(fields=['field', 'value_text']),
            models.Index(fields=['field', 'value_number']),
        ]
        unique_together = ['response', 'field']
        # Partitioning like parent table
    
    def __str__(self):
        return f"Response {self.response.id} - {self.field.label}"
    
    def set_value(self, value, encrypt=False):
        """
        Set response value based on field type.
        Automatically encrypts if field requires it or encrypt=True.
        """
        field_type = self.field.field_type
        
        # Determine which field to use
        if field_type in ['text', 'textarea', 'email', 'phone']:
            if encrypt or self.field.is_encrypted:
                self.value_text = self._encrypt(str(value))
                self.is_encrypted = True
            else:
                self.value_text = str(value)
        
        elif field_type == 'number':
            self.value_number = float(value)
        
        elif field_type == 'boolean':
            self.value_boolean = bool(value)
        
        elif field_type == 'date':
            self.value_date = value
        
        elif field_type == 'datetime':
            self.value_datetime = value
        
        elif field_type in ['single_choice', 'multiple_choice', 'dropdown', 'matrix']:
            self.value_json = value
        
        elif field_type == 'file_upload':
            self.file_url = value
    
    def get_value(self):
        """
        Get response value, decrypting if necessary.
        """
        field_type = self.field.field_type
        
        if field_type in ['text', 'textarea', 'email', 'phone']:
            if self.is_encrypted:
                return self._decrypt(self.value_text)
            return self.value_text
        
        elif field_type == 'number':
            return self.value_number
        
        elif field_type == 'boolean':
            return self.value_boolean
        
        elif field_type == 'date':
            return self.value_date
        
        elif field_type == 'datetime':
            return self.value_datetime
        
        elif field_type in ['single_choice', 'multiple_choice', 'dropdown', 'matrix']:
            return self.value_json
        
        elif field_type == 'file_upload':
            return self.file_url
        
        return None
    
    def _encrypt(self, value):
        """Encrypt sensitive data"""
        if not value:
            return ''
        
        # Get encryption key from settings
        key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
        if not key:
            raise ValueError('FIELD_ENCRYPTION_KEY not configured')
        
        fernet = Fernet(key.encode())
        encrypted = fernet.encrypt(value.encode())
        return base64.b64encode(encrypted).decode()
    
    def _decrypt(self, encrypted_value):
        """Decrypt sensitive data"""
        if not encrypted_value:
            return ''
        
        key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
        if not key:
            raise ValueError('FIELD_ENCRYPTION_KEY not configured')
        
        fernet = Fernet(key.encode())
        encrypted_bytes = base64.b64decode(encrypted_value.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()


class PartialResponse(TimeStampedModel):
    """
    Stores partial responses in Redis-like cache for quick resume.
    Periodically synced to DB for durability.
    
    This table is a backup/sync target. Primary storage should be Redis.
    """
    
    # Response reference
    response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='partial_snapshots'
    )
    
    # Snapshot data
    data = models.JSONField(
        help_text='Serialized response data: {field_id: value, ...}'
    )
    
    # Progress tracking
    progress_percentage = models.PositiveIntegerField(
        default=0,
        help_text='Completion percentage (0-100)'
    )
    current_section = models.ForeignKey(
        'surveys.Section',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Last section user was on'
    )
    
    # Expiration
    expires_at = models.DateTimeField(
        db_index=True,
        help_text='When this partial response expires'
    )
    
    # Metadata
    last_accessed_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'partial_responses'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['response', 'updated_at']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"Partial Response {self.response.id} - {self.progress_percentage}%"
    
    def is_expired(self):
        """Check if partial response has expired"""
        return timezone.now() > self.expires_at
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired partial responses (run as scheduled task)"""
        expired = cls.objects.filter(expires_at__lt=timezone.now())
        count = expired.count()
        expired.delete()
        return count
