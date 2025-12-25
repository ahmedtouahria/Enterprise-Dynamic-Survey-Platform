"""
Celery tasks for RBAC app.

Tasks for user management, role assignments, and access control monitoring.
"""

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='rbac.tasks.alert_inactive_users')
def alert_inactive_users(days=30):
    """
    Alert about users who haven't logged in for X days.
    Useful for security and license management.
    """
    from django.contrib.auth.models import User
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find users who haven't logged in recently
        inactive_users = User.objects.filter(
            is_active=True,
            last_login__lt=cutoff_date
        ).exclude(
            is_superuser=True
        )
        
        alerts = []
        for user in inactive_users:
            days_inactive = (timezone.now() - user.last_login).days if user.last_login else None
            alert = {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'days_inactive': days_inactive,
            }
            alerts.append(alert)
        
        # Cache alerts
        cache.set('inactive_user_alerts', alerts, timeout=86400)
        
        logger.info(f"Found {len(alerts)} inactive users")
        return {'alerts_count': len(alerts), 'alerts': alerts}
    
    except Exception as e:
        logger.error(f"Error checking inactive users: {str(e)}")
        raise


@shared_task(name='rbac.tasks.sync_user_permissions')
def sync_user_permissions(user_id):
    """
    Sync user permissions based on their roles.
    Rebuild permission cache for a user.
    """
    from django.contrib.auth.models import User
    from rbac.models import UserRole
    
    try:
        user = User.objects.get(id=user_id)
        
        # Get all permissions from user's roles
        user_roles = UserRole.objects.filter(user=user).select_related('role')
        
        all_permissions = set()
        for user_role in user_roles:
            role_permissions = user_role.role.permissions.all()
            all_permissions.update([perm.codename for perm in role_permissions])
        
        # Cache user permissions
        cache_key = f'user_permissions_{user_id}'
        cache.set(cache_key, list(all_permissions), timeout=3600)
        
        logger.info(f"Synced permissions for user {user.username}: {len(all_permissions)} permissions")
        return {
            'user_id': user_id,
            'username': user.username,
            'permission_count': len(all_permissions),
            'permissions': list(all_permissions)
        }
    
    except Exception as e:
        logger.error(f"Error syncing user permissions: {str(e)}")
        raise


@shared_task(name='rbac.tasks.audit_role_assignments')
def audit_role_assignments():
    """
    Audit current role assignments.
    Find users with multiple roles or unusual permissions.
    """
    from rbac.models import UserRole, Role
    from django.contrib.auth.models import User
    from django.db.models import Count
    
    try:
        # Users with multiple roles
        users_with_multiple_roles = User.objects.annotate(
            role_count=Count('userrole')
        ).filter(role_count__gt=1)
        
        multi_role_users = []
        for user in users_with_multiple_roles:
            roles = UserRole.objects.filter(user=user).select_related('role')
            multi_role_users.append({
                'user_id': user.id,
                'username': user.username,
                'role_count': roles.count(),
                'roles': [ur.role.name for ur in roles]
            })
        
        # Users without any roles
        users_without_roles = User.objects.filter(
            is_active=True,
            userrole__isnull=True
        ).exclude(is_superuser=True)
        
        no_role_users = [
            {'user_id': u.id, 'username': u.username, 'email': u.email}
            for u in users_without_roles
        ]
        
        # Role distribution
        role_distribution = Role.objects.annotate(
            user_count=Count('user_assignments')
        ).values('name', 'user_count').order_by('-user_count')
        
        audit_report = {
            'timestamp': timezone.now().isoformat(),
            'users_with_multiple_roles': {
                'count': len(multi_role_users),
                'users': multi_role_users
            },
            'users_without_roles': {
                'count': len(no_role_users),
                'users': no_role_users
            },
            'role_distribution': list(role_distribution),
        }
        
        # Cache report
        cache.set('role_assignment_audit', audit_report, timeout=3600)
        
        logger.info("Completed role assignment audit")
        return audit_report
    
    except Exception as e:
        logger.error(f"Error auditing role assignments: {str(e)}")
        raise


@shared_task(name='rbac.tasks.cache_role_permissions')
def cache_role_permissions():
    """
    Cache all role permissions for faster access control checks.
    Refresh the permission cache for all roles.
    """
    from rbac.models import Role
    
    try:
        roles = Role.objects.prefetch_related('permissions').all()
        
        role_permissions_map = {}
        for role in roles:
            permissions = [perm.codename for perm in role.permissions.all()]
            role_permissions_map[role.id] = {
                'role_name': role.name,
                'permissions': permissions,
                'permission_count': len(permissions)
            }
            
            # Cache individual role permissions
            cache.set(f'role_permissions_{role.id}', permissions, timeout=3600)
        
        # Cache the complete map
        cache.set('all_role_permissions', role_permissions_map, timeout=3600)
        
        logger.info(f"Cached permissions for {len(roles)} roles")
        return {
            'roles_cached': len(roles),
            'role_permissions': role_permissions_map
        }
    
    except Exception as e:
        logger.error(f"Error caching role permissions: {str(e)}")
        raise


@shared_task(name='rbac.tasks.generate_access_report')
def generate_access_report():
    """
    Generate comprehensive access control report.
    Shows who has access to what resources.
    """
    from rbac.models import Permission, Role, UserRole
    from django.contrib.auth.models import User
    
    try:
        # Total users and roles
        total_users = User.objects.filter(is_active=True).count()
        total_roles = Role.objects.count()
        total_permissions = Permission.objects.count()
        
        # Users by role
        role_breakdown = Role.objects.annotate(
            user_count=Count('user_assignments')
        ).values('name', 'user_count')
        
        # Most common permissions
        common_permissions = Permission.objects.annotate(
            role_count=Count('role')
        ).order_by('-role_count')[:10]
        
        permission_usage = [
            {
                'codename': perm.codename,
                'name': perm.name,
                'resource': perm.resource,
                'role_count': perm.role_count
            }
            for perm in common_permissions
        ]
        
        # Recent role assignments
        recent_assignments = UserRole.objects.select_related(
            'user', 'role', 'assigned_by'
        ).order_by('-created_at')[:20]
        
        recent = [
            {
                'user': ua.user.username,
                'role': ua.role.name,
                'assigned_by': ua.assigned_by.username if ua.assigned_by else None,
                'assigned_at': ua.created_at.isoformat()
            }
            for ua in recent_assignments
        ]
        
        report = {
            'generated_at': timezone.now().isoformat(),
            'summary': {
                'total_users': total_users,
                'total_roles': total_roles,
                'total_permissions': total_permissions,
            },
            'role_breakdown': list(role_breakdown),
            'permission_usage': permission_usage,
            'recent_assignments': recent,
        }
        
        # Cache report
        cache.set('access_control_report', report, timeout=3600)
        
        logger.info("Generated access control report")
        return report
    
    except Exception as e:
        logger.error(f"Error generating access report: {str(e)}")
        raise


@shared_task(name='rbac.tasks.cleanup_orphaned_roles')
def cleanup_orphaned_roles():
    """
    Find and optionally remove roles with no users or permissions.
    Helps maintain clean role hierarchy.
    """
    from rbac.models import Role
    from django.db.models import Count
    
    try:
        # Find roles with no users
        roles_no_users = Role.objects.annotate(
            user_count=Count('user_assignments')
        ).filter(user_count=0)
        
        # Find roles with no permissions
        roles_no_permissions = Role.objects.annotate(
            perm_count=Count('permissions')
        ).filter(perm_count=0)
        
        # Find roles with neither users nor permissions (truly orphaned)
        orphaned_roles = roles_no_users.filter(
            id__in=roles_no_permissions.values_list('id', flat=True)
        )
        
        orphaned_list = [
            {
                'id': role.id,
                'name': role.name,
                'created_at': role.created_at.isoformat()
            }
            for role in orphaned_roles
        ]
        
        report = {
            'timestamp': timezone.now().isoformat(),
            'roles_without_users': roles_no_users.count(),
            'roles_without_permissions': roles_no_permissions.count(),
            'orphaned_roles': {
                'count': len(orphaned_list),
                'roles': orphaned_list
            }
        }
        
        # Cache report
        cache.set('orphaned_roles_report', report, timeout=86400)
        
        logger.info(f"Found {len(orphaned_list)} orphaned roles")
        return report
    
    except Exception as e:
        logger.error(f"Error cleaning up orphaned roles: {str(e)}")
        raise


@shared_task(name='rbac.tasks.alert_permission_escalation')
def alert_permission_escalation():
    """
    Detect potential permission escalation attempts.
    Monitor for unusual permission grants.
    """
    from audits.models import AuditLog
    
    try:
        hour_ago = timezone.now() - timedelta(hours=1)
        
        # Check for recent permission grants
        permission_grants = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            action='PERMISSION_GRANT'
        ).select_related('user')
        
        alerts = []
        
        # Check if non-admin users are granting permissions
        for log in permission_grants:
            if log.user and not log.user.is_superuser:
                alerts.append({
                    'type': 'permission_grant_by_non_admin',
                    'user': log.username,
                    'description': log.description,
                    'timestamp': log.created_at.isoformat(),
                    'severity': 'high'
                })
        
        # Check for bulk permission changes
        bulk_changes = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            action__in=['PERMISSION_GRANT', 'PERMISSION_REVOKE']
        ).values('username').annotate(count=Count('id')).filter(count__gte=5)
        
        for change in bulk_changes:
            alerts.append({
                'type': 'bulk_permission_changes',
                'user': change['username'],
                'change_count': change['count'],
                'severity': 'medium'
            })
        
        if alerts:
            cache.set('permission_escalation_alerts', alerts, timeout=3600)
            logger.warning(f"Detected {len(alerts)} potential permission escalation attempts")
        
        return {'alerts_count': len(alerts), 'alerts': alerts}
    
    except Exception as e:
        logger.error(f"Error detecting permission escalation: {str(e)}")
        raise
