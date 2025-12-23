"""
Audit Log Models

Comprehensive audit trail for all system operations.
Append-only, immutable logs for compliance and debugging.
"""

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import json


class AuditLog(models.Model):
    """
    Comprehensive audit trail for all operations.
    
    Tracks:
    - Who performed the action
    - What action was performed
    - When it happened
    - Where (resource) it happened
    - How (old vs new values)
    
    Performance Considerations:
    - Partitioned by created_at (monthly)
    - Write-optimized (append-only)
    - Archived to cold storage after 6-12 months
    - No updates or deletes allowed
    """
    
    ACTION_TYPES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('VIEW', 'View'),
        ('EXPORT', 'Export'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('PERMISSION_GRANT', 'Permission Grant'),
        ('PERMISSION_REVOKE', 'Permission Revoke'),
    ]
    
    # Who
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        help_text='User who performed the action'
    )
    username = models.CharField(
        max_length=150,
        db_index=True,
        help_text='Username cached for historical reference'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # What
    action = models.CharField(
        max_length=50,
        choices=ACTION_TYPES,
        db_index=True
    )
    description = models.TextField(
        help_text='Human-readable description of the action'
    )
    
    # When
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='When the action occurred'
    )
    
    # Where (generic relation to any model)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional context
    resource_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Type of resource (cached from content_type)'
    )
    resource_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='ID of resource (for quick filtering)'
    )
    
    # How (change tracking)
    old_values = models.JSONField(
        null=True,
        blank=True,
        help_text='Previous values (for updates)'
    )
    new_values = models.JSONField(
        null=True,
        blank=True,
        help_text='New values (for creates/updates)'
    )
    
    # Multi-tenancy
    tenant_id = models.CharField(
        max_length=100,
        db_index=True
    )
    
    # Request metadata
    request_id = models.CharField(
        max_length=100,
        db_index=True,
        blank=True,
        help_text='Unique request ID for tracing'
    )
    session_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='User session ID'
    )
    
    # Additional metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional context (e.g., API endpoint, method)'
    )
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            # Primary query patterns
            models.Index(fields=['tenant_id', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['resource_type', 'resource_id', 'created_at']),
            models.Index(fields=['action', 'created_at']),
            
            # Composite indexes for common queries
            models.Index(fields=['tenant_id', 'action', 'created_at']),
            models.Index(fields=['tenant_id', 'resource_type', 'created_at']),
            
            # Request tracing
            models.Index(fields=['request_id']),
        ]
        # Table partitioning by month
        # Run: CREATE TABLE audit_logs_y2025m01 PARTITION OF audit_logs
        #      FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    
    def __str__(self):
        return f"{self.username} - {self.action} - {self.resource_type} - {self.created_at}"
    
    def save(self, *args, **kwargs):
        # Ensure no updates to existing records
        if self.pk is not None:
            raise ValueError('Audit logs are immutable and cannot be updated')
        
        # Cache username for historical reference
        if self.user and not self.username:
            self.username = self.user.username
        
        # Cache resource info
        if self.content_object:
            self.resource_type = self.content_type.model
            self.resource_id = str(self.object_id)
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Prevent deletion
        raise ValueError('Audit logs cannot be deleted')
    
    @classmethod
    def log(cls, user, action, resource=None, old_values=None, new_values=None, 
            description='', tenant_id='', request=None, **metadata):
        """
        Convenience method to create audit log entries.
        
        Usage:
            AuditLog.log(
                user=request.user,
                action='UPDATE',
                resource=survey,
                old_values={'title': 'Old Title'},
                new_values={'title': 'New Title'},
                description='Updated survey title',
                tenant_id='tenant_1',
                request=request
            )
        """
        log_data = {
            'user': user,
            'action': action,
            'description': description,
            'tenant_id': tenant_id,
            'old_values': old_values,
            'new_values': new_values,
            'metadata': metadata,
        }
        
        if resource:
            log_data['content_object'] = resource
        
        if request:
            log_data['ip_address'] = cls._get_client_ip(request)
            log_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
            log_data['request_id'] = request.META.get('HTTP_X_REQUEST_ID', '')
        
        return cls.objects.create(**log_data)
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def archive_old_logs(cls, months=12):
        """
        Archive logs older than specified months to cold storage.
        Should be run as periodic task.
        
        Returns:
            int: Number of logs archived
        """
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta
        
        cutoff_date = timezone.now() - relativedelta(months=months)
        old_logs = cls.objects.filter(created_at__lt=cutoff_date)
        
        # In production, export to S3/cold storage before deletion
        count = old_logs.count()
        
        # For now, just return count (don't actually delete)
        return count


class LoginAttempt(models.Model):
    """
    Track login attempts for security monitoring.
    Separate from main audit log for performance.
    """
    
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(blank=True)
    
    success = models.BooleanField(default=False, db_index=True)
    failure_reason = models.CharField(max_length=200, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Multi-tenancy
    tenant_id = models.CharField(max_length=100, db_index=True)
    
    class Meta:
        db_table = 'login_attempts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['username', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['tenant_id', 'success', 'created_at']),
        ]
    
    def __str__(self):
        status = 'Success' if self.success else 'Failed'
        return f"{self.username} - {status} - {self.created_at}"
    
    @classmethod
    def check_brute_force(cls, username=None, ip_address=None, window_minutes=15, max_attempts=5):
        """
        Check if there have been too many failed login attempts.
        
        Args:
            username: Username to check
            ip_address: IP address to check
            window_minutes: Time window to check
            max_attempts: Maximum failed attempts allowed
        
        Returns:
            bool: True if brute force detected
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(minutes=window_minutes)
        
        query = cls.objects.filter(
            created_at__gte=cutoff_time,
            success=False
        )
        
        if username:
            query = query.filter(username=username)
        
        if ip_address:
            query = query.filter(ip_address=ip_address)
        
        failed_count = query.count()
        return failed_count >= max_attempts
