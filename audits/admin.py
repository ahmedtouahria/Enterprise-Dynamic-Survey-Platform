"""
Audit Log Admin Configuration

Admin interface for viewing audit logs with:
- Comprehensive filtering
- Read-only access (immutable logs)
- Action timeline
- User activity tracking
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    """Admin for AuditLog model"""
    list_display = [
        'id', 'action_badge', 'username',
        'resource_display', 'description_short',
        'ip_address', 'created_at'
    ]
    list_filter = [
        'action', 'resource_type', 'created_at',
        'username'
    ]
    search_fields = [
        'username', 'description', 'resource_type',
        'resource_id', 'ip_address'
    ]
    readonly_fields = [
        'user', 'username', 'action', 'description',
        'resource_type', 'resource_id', 'content_type',
        'object_id', 'ip_address', 'user_agent',
        'tenant_id', 'old_values', 'new_values',
        'changes_display', 'created_at'
    ]
    
    fieldsets = (
        ('Action Information', {
            'fields': ('action', 'description', 'created_at')
        }),
        ('User Information', {
            'fields': ('user', 'username', 'ip_address', 'user_agent')
        }),
        ('Resource', {
            'fields': (
                'resource_type', 'resource_id',
                'content_type', 'object_id'
            )
        }),
        ('Changes', {
            'fields': ('old_values', 'new_values', 'changes_display'),
            'classes': ['collapse']
        }),
        ('Multi-tenancy', {
            'fields': ('tenant_id',),
            'classes': ['collapse']
        }),
    )
    
    date_hierarchy = 'created_at'
    
    @display(description="Action", label=True)
    def action_badge(self, obj):
        colors = {
            'CREATE': 'success',
            'UPDATE': 'info',
            'DELETE': 'danger',
            'VIEW': 'warning',
            'EXPORT': 'info',
            'LOGIN': 'success',
            'LOGOUT': 'warning',
            'PERMISSION_GRANT': 'success',
            'PERMISSION_REVOKE': 'danger'
        }
        return colors.get(obj.action, 'info')
    
    def resource_display(self, obj):
        return f"{obj.resource_type}:{obj.resource_id}"
    resource_display.short_description = 'Resource'
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'
    
    def changes_display(self, obj):
        if not obj.old_values and not obj.new_values:
            return 'No changes recorded'
        
        html = '<table style="width:100%; border-collapse: collapse;">'
        html += '<tr><th style="text-align:left; padding:5px; border:1px solid #ddd;">Field</th>'
        html += '<th style="text-align:left; padding:5px; border:1px solid #ddd;">Old Value</th>'
        html += '<th style="text-align:left; padding:5px; border:1px solid #ddd;">New Value</th></tr>'
        
        all_keys = set(list(obj.old_values.keys()) + list(obj.new_values.keys()))
        
        for key in all_keys:
            old_val = obj.old_values.get(key, '-')
            new_val = obj.new_values.get(key, '-')
            html += f'<tr><td style="padding:5px; border:1px solid #ddd;"><strong>{key}</strong></td>'
            html += f'<td style="padding:5px; border:1px solid #ddd;">{old_val}</td>'
            html += f'<td style="padding:5px; border:1px solid #ddd;">{new_val}</td></tr>'
        
        html += '</table>'
        return format_html(html)
    changes_display.short_description = 'Changes Detail'
    
    def has_add_permission(self, request):
        # Audit logs are created by the system only
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Audit logs are immutable
        return False
    
    def has_change_permission(self, request, obj=None):
        # Audit logs are immutable
        return False

