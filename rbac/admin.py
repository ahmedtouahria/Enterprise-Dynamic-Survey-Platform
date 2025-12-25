"""
RBAC Admin Configuration

Admin interface for role-based access control with:
- Permission management
- Role hierarchy
- User role assignments
- Tenant isolation
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from .models import Permission, Role, UserRole


class PermissionInline(TabularInline):
    """Inline for role permissions"""
    model = Role.permissions.through
    extra = 0


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    """Admin for Permission model"""
    list_display = [
        'codename', 'name', 'resource_badge',
        'action', 'is_system_permission', 'role_count'
    ]
    list_filter = ['resource', 'action', 'is_system_permission']
    search_fields = ['codename', 'name', 'description']
    readonly_fields = ['resource', 'action', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('codename', 'name', 'description')
        }),
        ('Classification', {
            'fields': ('resource', 'action', 'is_system_permission')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    @display(description="Resource", label=True)
    def resource_badge(self, obj):
        colors = {
            'survey': 'info',
            'response': 'success',
            'analytics': 'warning',
            'user': 'danger'
        }
        return colors.get(obj.resource, 'info')
    
    @display(description="Roles")
    def role_count(self, obj):
        return obj.role_set.count()
    
    def has_delete_permission(self, request, obj=None):
        # System permissions cannot be deleted
        if obj and obj.is_system_permission:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    """Admin for Role model"""
    list_display = [
        'name', 'tenant_id', 'user_count',
        'permission_count', 'created_at'
    ]
    list_filter = ['tenant_id', 'created_at']
    search_fields = ['name', 'description', 'tenant_id']
    readonly_fields = ['created_at', 'updated_at', 'permission_summary']
    filter_horizontal = ['permissions']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description')
        }),
        ('Permissions', {
            'fields': ('permissions', 'permission_summary')
        }),
        ('Multi-tenancy', {
            'fields': ('tenant_id',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    @display(description="Users")
    def user_count(self, obj):
        return obj.user_assignments.count()
    
    @display(description="Permissions")
    def permission_count(self, obj):
        return obj.permissions.count()
    
    def permission_summary(self, obj):
        permissions = obj.permissions.all()
        by_resource = {}
        for perm in permissions:
            if perm.resource not in by_resource:
                by_resource[perm.resource] = []
            by_resource[perm.resource].append(perm.action)
        
        html = '<ul>'
        for resource, actions in by_resource.items():
            html += f'<li><strong>{resource}:</strong> {", ".join(actions)}</li>'
        html += '</ul>'
        
        return format_html(html) if by_resource else '-'
    permission_summary.short_description = 'Permission Summary'


@admin.register(UserRole)
class UserRoleAdmin(ModelAdmin):
    """Admin for UserRole model"""
    list_display = [
        'user', 'role', 'tenant_id',
        'assigned_by', 'created_at'
    ]
    list_filter = ['role', 'tenant_id', 'created_at']
    search_fields = [
        'user__username', 'user__email',
        'role__name', 'tenant_id'
    ]
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['user', 'role', 'assigned_by']
    
    fieldsets = (
        ('Assignment', {
            'fields': ('user', 'role', 'assigned_by')
        }),
        ('Multi-tenancy', {
            'fields': ('tenant_id',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)

