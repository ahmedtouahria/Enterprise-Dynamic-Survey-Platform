"""
Celery tasks for audits app.

Tasks for system monitoring, health checks, and log management.
"""

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='audits.tasks.cleanup_old_audit_logs')
def cleanup_old_audit_logs(days=365):
    """
    Archive or delete old audit logs to manage database size.
    Default: keep logs for 1 year (365 days).
    """
    from audits.models import AuditLog
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_logs = AuditLog.objects.filter(created_at__lt=cutoff_date)
        count = old_logs.count()
        
        # TODO: Archive to external storage (S3, etc.) before deleting
        # For now, just delete
        old_logs.delete()
        
        logger.info(f"Deleted {count} old audit logs")
        return {'deleted_count': count}
    
    except Exception as e:
        logger.error(f"Error cleaning up audit logs: {str(e)}")
        raise


@shared_task(name='audits.tasks.check_system_health')
def check_system_health():
    """
    Perform system health checks.
    Monitor database, cache, and application status.
    """
    from django.db import connection
    from django.contrib.auth.models import User
    from surveys.models import Survey
    from responses.models import SurveyResponse
    
    health_status = {
        'timestamp': timezone.now().isoformat(),
        'status': 'healthy',
        'checks': {}
    }
    
    try:
        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status['checks']['database'] = {'status': 'ok', 'latency_ms': 0}
        except Exception as e:
            health_status['checks']['database'] = {'status': 'error', 'error': str(e)}
            health_status['status'] = 'unhealthy'
        
        # Cache check
        try:
            cache.set('health_check', 'ok', timeout=60)
            result = cache.get('health_check')
            if result == 'ok':
                health_status['checks']['cache'] = {'status': 'ok'}
            else:
                health_status['checks']['cache'] = {'status': 'error', 'error': 'Cache read/write failed'}
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['checks']['cache'] = {'status': 'error', 'error': str(e)}
            health_status['status'] = 'unhealthy'
        
        # Application metrics
        try:
            health_status['checks']['metrics'] = {
                'total_users': User.objects.count(),
                'active_surveys': Survey.objects.filter(status='published').count(),
                'responses_last_24h': SurveyResponse.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=1)
                ).count(),
            }
        except Exception as e:
            health_status['checks']['metrics'] = {'status': 'error', 'error': str(e)}
        
        # Cache health status
        cache.set('system_health', health_status, timeout=1800)  # 30 minutes
        
        logger.info(f"System health check: {health_status['status']}")
        return health_status
    
    except Exception as e:
        logger.error(f"Error performing health check: {str(e)}")
        raise


@shared_task(name='audits.tasks.generate_audit_summary')
def generate_audit_summary(days=7):
    """
    Generate summary of audit log activity.
    Shows top actions, users, and trends.
    """
    from audits.models import AuditLog
    from django.db.models import Count
    
    try:
        start_date = timezone.now() - timedelta(days=days)
        
        logs = AuditLog.objects.filter(created_at__gte=start_date)
        
        # Top actions
        top_actions = logs.values('action').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Top users
        top_users = logs.values('username').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Actions by resource type
        resource_activity = logs.values('resource_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Daily activity trend
        daily_activity = logs.extra(
            select={'day': 'DATE(created_at)'}
        ).values('day').annotate(count=Count('id')).order_by('-day')
        
        summary = {
            'period_days': days,
            'start_date': start_date.date().isoformat(),
            'end_date': timezone.now().date().isoformat(),
            'total_events': logs.count(),
            'top_actions': list(top_actions),
            'top_users': list(top_users),
            'resource_activity': list(resource_activity),
            'daily_trend': list(daily_activity),
            'generated_at': timezone.now().isoformat(),
        }
        
        # Cache summary
        cache.set(f'audit_summary_{days}d', summary, timeout=3600)
        
        logger.info(f"Generated audit summary for {days} days")
        return summary
    
    except Exception as e:
        logger.error(f"Error generating audit summary: {str(e)}")
        raise


@shared_task(name='audits.tasks.detect_suspicious_activity')
def detect_suspicious_activity():
    """
    Detect potentially suspicious activity patterns.
    Alert on unusual login attempts, excessive API calls, etc.
    """
    from audits.models import AuditLog
    from django.db.models import Count
    
    try:
        hour_ago = timezone.now() - timedelta(hours=1)
        
        alerts = []
        
        # Check for excessive failed login attempts
        failed_logins = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            action='LOGIN',
            description__icontains='failed'
        ).values('username', 'ip_address').annotate(
            count=Count('id')
        ).filter(count__gte=5)  # 5+ failed attempts
        
        for login in failed_logins:
            alerts.append({
                'type': 'excessive_failed_logins',
                'username': login['username'],
                'ip_address': login['ip_address'],
                'count': login['count'],
                'severity': 'high'
            })
        
        # Check for unusual deletion activity
        bulk_deletes = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            action='DELETE'
        ).values('username').annotate(
            count=Count('id')
        ).filter(count__gte=10)  # 10+ deletions in 1 hour
        
        for delete in bulk_deletes:
            alerts.append({
                'type': 'bulk_deletion',
                'username': delete['username'],
                'count': delete['count'],
                'severity': 'medium'
            })
        
        # Check for permission changes
        permission_changes = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            action__in=['PERMISSION_GRANT', 'PERMISSION_REVOKE']
        ).count()
        
        if permission_changes > 5:
            alerts.append({
                'type': 'excessive_permission_changes',
                'count': permission_changes,
                'severity': 'medium'
            })
        
        # Cache alerts
        if alerts:
            cache.set('security_alerts', alerts, timeout=3600)
            logger.warning(f"Detected {len(alerts)} suspicious activities")
        else:
            logger.info("No suspicious activity detected")
        
        return {'alerts_count': len(alerts), 'alerts': alerts}
    
    except Exception as e:
        logger.error(f"Error detecting suspicious activity: {str(e)}")
        raise


@shared_task(name='audits.tasks.generate_compliance_report')
def generate_compliance_report():
    """
    Generate compliance report for data access and modifications.
    Useful for GDPR, HIPAA, or other regulatory requirements.
    """
    from audits.models import AuditLog
    from django.db.models import Count
    
    try:
        month_ago = timezone.now() - timedelta(days=30)
        
        logs = AuditLog.objects.filter(created_at__gte=month_ago)
        
        # Data access events
        view_events = logs.filter(action='VIEW').count()
        
        # Data modification events
        create_events = logs.filter(action='CREATE').count()
        update_events = logs.filter(action='UPDATE').count()
        delete_events = logs.filter(action='DELETE').count()
        
        # Export events
        export_events = logs.filter(action='EXPORT').count()
        
        # Users with data access
        users_with_access = logs.values('username').distinct().count()
        
        report = {
            'period': '30_days',
            'start_date': month_ago.date().isoformat(),
            'end_date': timezone.now().date().isoformat(),
            'total_events': logs.count(),
            'data_access_events': view_events,
            'data_modifications': {
                'created': create_events,
                'updated': update_events,
                'deleted': delete_events,
            },
            'export_events': export_events,
            'users_with_access': users_with_access,
            'generated_at': timezone.now().isoformat(),
        }
        
        # Cache report
        cache.set('compliance_report', report, timeout=86400)
        
        logger.info("Generated compliance report")
        return report
    
    except Exception as e:
        logger.error(f"Error generating compliance report: {str(e)}")
        raise


@shared_task(name='audits.tasks.monitor_api_usage')
def monitor_api_usage():
    """
    Monitor API endpoint usage and performance.
    Track request counts, errors, and response times.
    """
    from audits.models import AuditLog
    
    try:
        hour_ago = timezone.now() - timedelta(hours=1)
        
        # Get API-related logs
        api_logs = AuditLog.objects.filter(
            created_at__gte=hour_ago,
            resource_type__in=['survey', 'response', 'user']
        )
        
        # Count by action type
        action_counts = api_logs.values('action', 'resource_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Count by user
        user_activity = api_logs.values('username').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        usage_report = {
            'period': 'last_hour',
            'timestamp': timezone.now().isoformat(),
            'total_requests': api_logs.count(),
            'requests_by_action': list(action_counts),
            'top_users': list(user_activity),
        }
        
        # Cache usage report
        cache.set('api_usage_report', usage_report, timeout=3600)
        
        logger.info(f"Monitored API usage: {api_logs.count()} requests in last hour")
        return usage_report
    
    except Exception as e:
        logger.error(f"Error monitoring API usage: {str(e)}")
        raise
