"""
Celery configuration for the survey platform.

This module configures Celery for background task processing.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('survey_platform')

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Celery Beat Schedule - Periodic Tasks
app.conf.beat_schedule = {
    # Data Cleanup Tasks
    'cleanup-abandoned-responses-daily': {
        'task': 'responses.tasks.cleanup_abandoned_responses',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'cleanup-expired-sessions-daily': {
        'task': 'responses.tasks.cleanup_expired_sessions',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    'archive-old-surveys-weekly': {
        'task': 'surveys.tasks.archive_old_surveys',
        'schedule': crontab(day_of_week=0, hour=4, minute=0),  # Sunday at 4 AM
    },
    'cleanup-old-audit-logs-monthly': {
        'task': 'audits.tasks.cleanup_old_audit_logs',
        'schedule': crontab(day_of_month=1, hour=5, minute=0),  # 1st of month at 5 AM
    },
    
    # Reporting Tasks
    'generate-daily-report': {
        'task': 'surveys.tasks.generate_daily_report',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
    'generate-weekly-report': {
        'task': 'surveys.tasks.generate_weekly_report',
        'schedule': crontab(day_of_week=1, hour=7, minute=0),  # Monday at 7 AM
    },
    'generate-monthly-report': {
        'task': 'surveys.tasks.generate_monthly_report',
        'schedule': crontab(day_of_month=1, hour=8, minute=0),  # 1st of month at 8 AM
    },
    'cache-survey-statistics-hourly': {
        'task': 'surveys.tasks.cache_survey_statistics',
        'schedule': crontab(minute=0),  # Every hour
    },
    
    # Alerting Tasks
    'check-survey-deadlines-daily': {
        'task': 'surveys.tasks.check_survey_deadlines',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
    'alert-low-response-rates-daily': {
        'task': 'responses.tasks.alert_low_response_rates',
        'schedule': crontab(hour=10, minute=0),  # Daily at 10 AM
    },
    'check-system-health-hourly': {
        'task': 'audits.tasks.check_system_health',
        'schedule': crontab(minute=30),  # Every hour at :30
    },
    'alert-inactive-users-weekly': {
        'task': 'rbac.tasks.alert_inactive_users',
        'schedule': crontab(day_of_week=1, hour=11, minute=0),  # Monday at 11 AM
    },
}

# Celery Configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery"""
    print(f'Request: {self.request!r}')

