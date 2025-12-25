"""
Celery tasks for surveys app.

Tasks for survey management, reporting, and alerting.
"""

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Q, Avg
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='surveys.tasks.cache_survey_statistics')
def cache_survey_statistics():
    """
    Cache survey statistics for faster dashboard loading.
    Runs every hour to keep statistics fresh.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    
    try:
        # Cache survey counts by status
        survey_stats = {
            'total': Survey.objects.count(),
            'published': Survey.objects.filter(status='published').count(),
            'draft': Survey.objects.filter(status='draft').count(),
            'archived': Survey.objects.filter(status='archived').count(),
        }
        cache.set('survey_statistics', survey_stats, timeout=3600)  # 1 hour
        
        # Cache response statistics
        response_stats = {
            'total': SurveyResponse.objects.count(),
            'completed': SurveyResponse.objects.filter(status='completed').count(),
            'in_progress': SurveyResponse.objects.filter(status='in_progress').count(),
            'abandoned': SurveyResponse.objects.filter(status='abandoned').count(),
        }
        cache.set('response_statistics', response_stats, timeout=3600)
        
        # Cache top performing surveys
        top_surveys = Survey.objects.filter(
            status='published'
        ).annotate(
            response_count=Count('responses')
        ).order_by('-response_count')[:10]
        
        top_surveys_data = [
            {
                'id': s.id,
                'title': s.title,
                'response_count': s.response_count,
            }
            for s in top_surveys
        ]
        cache.set('top_surveys', top_surveys_data, timeout=3600)
        
        logger.info("Successfully cached survey statistics")
        return "Statistics cached successfully"
    
    except Exception as e:
        logger.error(f"Error caching survey statistics: {str(e)}")
        raise


@shared_task(name='surveys.tasks.generate_daily_report')
def generate_daily_report():
    """
    Generate daily report of survey activity.
    Includes new responses, completed surveys, and engagement metrics.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    
    try:
        yesterday = timezone.now() - timedelta(days=1)
        
        # New surveys created
        new_surveys = Survey.objects.filter(created_at__gte=yesterday).count()
        
        # New responses
        new_responses = SurveyResponse.objects.filter(created_at__gte=yesterday).count()
        completed_responses = SurveyResponse.objects.filter(
            submitted_at__gte=yesterday,
            status='completed'
        ).count()
        
        # Calculate completion rate
        completion_rate = (completed_responses / new_responses * 100) if new_responses > 0 else 0
        
        report = {
            'date': yesterday.date().isoformat(),
            'new_surveys': new_surveys,
            'new_responses': new_responses,
            'completed_responses': completed_responses,
            'completion_rate': round(completion_rate, 2),
            'generated_at': timezone.now().isoformat(),
        }
        
        # Cache the report
        cache.set('daily_report', report, timeout=86400)  # 24 hours
        
        logger.info(f"Daily report generated: {report}")
        return report
    
    except Exception as e:
        logger.error(f"Error generating daily report: {str(e)}")
        raise


@shared_task(name='surveys.tasks.generate_weekly_report')
def generate_weekly_report():
    """
    Generate weekly summary report.
    Includes trends, top surveys, and user engagement.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    
    try:
        week_ago = timezone.now() - timedelta(days=7)
        
        # Weekly metrics
        new_surveys = Survey.objects.filter(created_at__gte=week_ago).count()
        total_responses = SurveyResponse.objects.filter(created_at__gte=week_ago).count()
        completed_responses = SurveyResponse.objects.filter(
            submitted_at__gte=week_ago,
            status='completed'
        ).count()
        
        # Most active surveys
        active_surveys = Survey.objects.filter(
            responses__created_at__gte=week_ago
        ).annotate(
            weekly_responses=Count('responses')
        ).order_by('-weekly_responses')[:5]
        
        report = {
            'period': 'weekly',
            'start_date': week_ago.date().isoformat(),
            'end_date': timezone.now().date().isoformat(),
            'new_surveys': new_surveys,
            'total_responses': total_responses,
            'completed_responses': completed_responses,
            'completion_rate': round((completed_responses / total_responses * 100), 2) if total_responses > 0 else 0,
            'top_surveys': [
                {'id': s.id, 'title': s.title, 'responses': s.weekly_responses}
                for s in active_surveys
            ],
            'generated_at': timezone.now().isoformat(),
        }
        
        cache.set('weekly_report', report, timeout=604800)  # 7 days
        
        logger.info(f"Weekly report generated")
        return report
    
    except Exception as e:
        logger.error(f"Error generating weekly report: {str(e)}")
        raise


@shared_task(name='surveys.tasks.generate_monthly_report')
def generate_monthly_report():
    """
    Generate comprehensive monthly report.
    Includes detailed analytics and trends.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    
    try:
        month_ago = timezone.now() - timedelta(days=30)
        
        # Monthly metrics
        new_surveys = Survey.objects.filter(created_at__gte=month_ago).count()
        total_responses = SurveyResponse.objects.filter(created_at__gte=month_ago).count()
        unique_respondents = SurveyResponse.objects.filter(
            created_at__gte=month_ago,
            user__isnull=False
        ).values('user').distinct().count()
        
        report = {
            'period': 'monthly',
            'start_date': month_ago.date().isoformat(),
            'end_date': timezone.now().date().isoformat(),
            'new_surveys': new_surveys,
            'total_responses': total_responses,
            'unique_respondents': unique_respondents,
            'generated_at': timezone.now().isoformat(),
        }
        
        cache.set('monthly_report', report, timeout=2592000)  # 30 days
        
        logger.info(f"Monthly report generated")
        return report
    
    except Exception as e:
        logger.error(f"Error generating monthly report: {str(e)}")
        raise


@shared_task(name='surveys.tasks.check_survey_deadlines')
def check_survey_deadlines():
    """
    Check for surveys approaching their deadline and send alerts.
    Alert when deadline is within 3 days.
    """
    from surveys.models import Survey
    
    try:
        now = timezone.now()
        three_days = now + timedelta(days=3)
        
        # Find surveys with upcoming deadlines
        upcoming_deadlines = Survey.objects.filter(
            status='published',
            submission_deadline__isnull=False,
            submission_deadline__gte=now,
            submission_deadline__lte=three_days
        ).select_related('created_by')
        
        alerts = []
        for survey in upcoming_deadlines:
            days_remaining = (survey.submission_deadline - now).days
            alert = {
                'survey_id': survey.id,
                'survey_title': survey.title,
                'deadline': survey.submission_deadline.isoformat(),
                'days_remaining': days_remaining,
                'owner': survey.created_by.email if survey.created_by else None,
            }
            alerts.append(alert)
            
            # Cache individual alert
            cache.set(f'deadline_alert_{survey.id}', alert, timeout=86400)
        
        # Cache all alerts
        cache.set('survey_deadline_alerts', alerts, timeout=3600)
        
        logger.info(f"Found {len(alerts)} surveys with upcoming deadlines")
        return {'alerts_count': len(alerts), 'alerts': alerts}
    
    except Exception as e:
        logger.error(f"Error checking survey deadlines: {str(e)}")
        raise


@shared_task(name='surveys.tasks.archive_old_surveys')
def archive_old_surveys(days=180):
    """
    Archive surveys that haven't been modified in X days and are in draft status.
    Default: 180 days (6 months)
    """
    from surveys.models import Survey
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_drafts = Survey.objects.filter(
            status='draft',
            updated_at__lt=cutoff_date
        )
        
        count = old_drafts.count()
        old_drafts.update(status='archived')
        
        # Clear related caches
        cache.delete('survey_statistics')
        
        logger.info(f"Archived {count} old draft surveys")
        return {'archived_count': count}
    
    except Exception as e:
        logger.error(f"Error archiving old surveys: {str(e)}")
        raise


@shared_task(name='surveys.tasks.export_survey_responses')
def export_survey_responses(survey_id, format='csv'):
    """
    Export survey responses to CSV or JSON.
    Can be called manually or scheduled.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    import json
    import csv
    from io import StringIO
    
    try:
        survey = Survey.objects.get(id=survey_id)
        responses = SurveyResponse.objects.filter(
            survey=survey,
            status='completed'
        ).select_related('user').prefetch_related('items__field')
        
        if format == 'json':
            data = []
            for response in responses:
                response_data = {
                    'response_id': response.id,
                    'submitted_at': response.submitted_at.isoformat() if response.submitted_at else None,
                    'user': response.user.username if response.user else response.respondent_email,
                    'answers': {
                        item.field.label: item.get_value()
                        for item in response.items.all()
                    }
                }
                data.append(response_data)
            
            export_data = json.dumps(data, indent=2)
        
        else:  # CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Response ID', 'Submitted At', 'User', 'Answers'])
            
            # Write data
            for response in responses:
                answers = '; '.join([
                    f"{item.field.label}: {item.get_value()}"
                    for item in response.items.all()
                ])
                writer.writerow([
                    response.id,
                    response.submitted_at.isoformat() if response.submitted_at else '',
                    response.user.username if response.user else response.respondent_email,
                    answers
                ])
            
            export_data = output.getvalue()
        
        # Cache the export for 1 hour
        cache_key = f'export_{survey_id}_{format}'
        cache.set(cache_key, export_data, timeout=3600)
        
        logger.info(f"Exported {responses.count()} responses for survey {survey_id}")
        return {'survey_id': survey_id, 'response_count': responses.count(), 'cache_key': cache_key}
    
    except Exception as e:
        logger.error(f"Error exporting survey responses: {str(e)}")
        raise
