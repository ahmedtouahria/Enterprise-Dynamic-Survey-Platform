"""
RBAC Models

Role-Based Access Control for survey platform.
Supports:
- Fine-grained permissions
- Role hierarchy
- Multi-tenancy
- Custom permission checks
"""

from django.db import models
from django.contrib.auth.models import User


class TimeStampedModel(models.Model):
    """Abstract base model with timestamp fields"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Permission(TimeStampedModel):
    """
    Granular permissions for survey operations.
    
    Examples:
    - survey.create
    - survey.edit
    - survey.delete
    - survey.view
    - submission.create
    - submission.view
    - submission.edit_own
    - analytics.view
    - analytics.export
    - user.manage
    """
    
    codename = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='Dot notation: resource.action (e.g., survey.create)'
    )
    name = models.CharField(
        max_length=255,
        help_text='Human-readable permission name'
    )
    description = models.TextField(blank=True)
    
    # Permission grouping
    resource = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Resource type (survey, submission, analytics, etc.)'
    )
    action = models.CharField(
        max_length=50,
        help_text='Action on resource (create, view, edit, delete, etc.)'
    )
    
    # Scope
    is_system_permission = models.BooleanField(
        default=False,
        help_text='System permissions cannot be deleted'
    )
    
    class Meta:
        db_table = 'permissions'
        ordering = ['resource', 'action']
        indexes = [
            models.Index(fields=['resource', 'action']),
        ]
    
    def __str__(self):
        return self.codename
    
    def save(self, *args, **kwargs):
        # Auto-populate resource and action from codename
        if '.' in self.codename:
            parts = self.codename.split('.')
            self.resource = parts[0]
            self.action = '.'.join(parts[1:])
        super().save(*args, **kwargs)


class Role(TimeStampedModel):
    """
    Roles group permissions and can be assigned to users.
    Supports role hierarchy (e.g., Admin > Creator > Analyst).
    """
    
    name = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Role name (e.g., Admin, Survey Creator, Analyst)'
    )
    description = models.TextField(blank=True)
    
    # Multi-tenancy
    tenant_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Empty for global roles, specific for tenant roles'
    )
    
    # Role hierarchy
    parent_role = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_roles',
        help_text='Parent role (inherits all permissions)'
    )
    
    # Permissions
    permissions = models.ManyToManyField(
        Permission,
        related_name='roles',
        blank=True
    )
    
    # System role
    is_system_role = models.BooleanField(
        default=False,
        help_text='System roles cannot be deleted'
    )
    
    class Meta:
        db_table = 'roles'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant_id', 'name']),
        ]
        unique_together = ['name', 'tenant_id']
    
    def __str__(self):
        return f"{self.name} ({self.tenant_id or 'Global'})"
    
    def get_all_permissions(self):
        """
        Get all permissions including inherited from parent roles.
        Returns a queryset of Permission objects.
        """
        permissions = set(self.permissions.all())
        
        # Add parent permissions recursively
        if self.parent_role:
            permissions.update(self.parent_role.get_all_permissions())
        
        return permissions
    
    def has_permission(self, permission_codename):
        """Check if role has specific permission"""
        all_permissions = self.get_all_permissions()
        return any(p.codename == permission_codename for p in all_permissions)


class UserRole(TimeStampedModel):
    """
    Assignment of roles to users with optional scope restrictions.
    
    Supports:
    - Multiple roles per user
    - Scoped permissions (e.g., can edit only own surveys)
    - Tenant-level access
    """
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='role_assignments'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='user_assignments'
    )
    
    # Multi-tenancy
    tenant_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Tenant this role applies to'
    )
    
    # Scope restrictions
    scope = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional scope restrictions (e.g., {"survey_ids": [1, 2, 3]})'
    )
    
    # Time-based access
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this role becomes active'
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this role expires'
    )
    
    # Assignment metadata
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='role_assignments_made'
    )
    
    class Meta:
        db_table = 'user_roles'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'tenant_id']),
            models.Index(fields=['role', 'tenant_id']),
            models.Index(fields=['user', 'role', 'tenant_id']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.role.name} ({self.tenant_id})"
    
    def is_active(self):
        """Check if role assignment is currently active"""
        from django.utils import timezone
        now = timezone.now()
        
        if self.valid_from and self.valid_from > now:
            return False
        
        if self.valid_until and self.valid_until < now:
            return False
        
        return True


class PermissionCheck:
    """
    Utility class for checking user permissions.
    
    Usage:
        checker = PermissionCheck(user, tenant_id='tenant_1')
        if checker.has_permission('survey.create'):
            # Allow action
        
        if checker.has_permission('survey.edit', survey_id=123):
            # Check with scope
    """
    
    def __init__(self, user, tenant_id):
        self.user = user
        self.tenant_id = tenant_id
        self._permissions_cache = None
    
    def get_user_permissions(self):
        """Get all permissions for user in current tenant"""
        if self._permissions_cache is not None:
            return self._permissions_cache
        
        # Get active role assignments
        role_assignments = UserRole.objects.filter(
            user=self.user,
            tenant_id=self.tenant_id
        ).select_related('role')
        
        # Filter active assignments
        active_assignments = [
            assignment for assignment in role_assignments
            if assignment.is_active()
        ]
        
        # Collect all permissions from roles
        permissions = set()
        for assignment in active_assignments:
            permissions.update(assignment.role.get_all_permissions())
        
        self._permissions_cache = permissions
        return permissions
    
    def has_permission(self, permission_codename, **scope):
        """
        Check if user has specific permission.
        
        Args:
            permission_codename: Permission to check (e.g., 'survey.edit')
            **scope: Additional scope checks (e.g., survey_id=123)
        
        Returns:
            bool: True if user has permission
        """
        permissions = self.get_user_permissions()
        
        # Check if permission exists
        has_perm = any(p.codename == permission_codename for p in permissions)
        if not has_perm:
            return False
        
        # If scope provided, check scope restrictions
        if scope:
            # Get role assignments with scope
            assignments = UserRole.objects.filter(
                user=self.user,
                tenant_id=self.tenant_id,
                role__permissions__codename=permission_codename
            )
            
            # Check if any assignment allows the scope
            for assignment in assignments:
                if not assignment.is_active():
                    continue
                
                # If no scope restrictions, allow
                if not assignment.scope:
                    return True
                
                # Check scope restrictions
                scope_valid = True
                for key, value in scope.items():
                    if key in assignment.scope:
                        allowed_values = assignment.scope[key]
                        if value not in allowed_values:
                            scope_valid = False
                            break
                
                if scope_valid:
                    return True
            
            return False
        
        return True
