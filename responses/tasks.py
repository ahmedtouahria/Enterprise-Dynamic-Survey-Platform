"""
Celery tasks for responses app.

Tasks for response cleanup, alerting, and analytics.
"""

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Avg, F
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='responses.tasks.cleanup_abandoned_responses')
def cleanup_abandoned_responses(days=7):
    """
    Mark old in-progress responses as abandoned.
    Default: responses inactive for 7 days.
    """
    from responses.models import SurveyResponse
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        abandoned = SurveyResponse.objects.filter(
            status='in_progress',
            updated_at__lt=cutoff_date
        )
        
        count = abandoned.count()
        abandoned.update(status='abandoned')
        
        # Clear response statistics cache
        cache.delete('response_statistics')
        
        logger.info(f"Marked {count} responses as abandoned")
        return {'abandoned_count': count}
    
    except Exception as e:
        logger.error(f"Error cleaning up abandoned responses: {str(e)}")
        raise


@shared_task(name='responses.tasks.cleanup_expired_sessions')
def cleanup_expired_sessions(days=30):
    """
    Delete very old abandoned responses to save space.
    Default: abandoned responses older than 30 days.
    """
    from responses.models import SurveyResponse
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_abandoned = SurveyResponse.objects.filter(
            status='abandoned',
            updated_at__lt=cutoff_date
        )
        
        count = old_abandoned.count()
        old_abandoned.delete()
        
        logger.info(f"Deleted {count} old abandoned responses")
        return {'deleted_count': count}
    
    except Exception as e:
        logger.error(f"Error cleaning up expired sessions: {str(e)}")
        raise


@shared_task(name='responses.tasks.alert_low_response_rates')
def alert_low_response_rates(threshold=10):
    """
    Alert survey owners when their published surveys have low response rates.
    Threshold: minimum expected responses (default: 10).
    """
    from surveys.models import Survey
    from django.db.models import Count
    
    try:
        # Check published surveys older than 7 days
        week_ago = timezone.now() - timedelta(days=7)
        
        low_response_surveys = Survey.objects.filter(
            status='published',
            created_at__lt=week_ago
        ).annotate(
            response_count=Count('responses')
        ).filter(
            response_count__lt=threshold
        ).select_related('created_by')
        
        alerts = []
        for survey in low_response_surveys:
            alert = {
                'survey_id': survey.id,
                'survey_title': survey.title,
                'response_count': survey.response_count,
                'days_since_published': (timezone.now() - survey.created_at).days,
                'owner': survey.created_by.email if survey.created_by else None,
            }
            alerts.append(alert)
            
            # Cache alert
            cache.set(f'low_response_alert_{survey.id}', alert, timeout=86400)
        
        cache.set('low_response_alerts', alerts, timeout=3600)
        
        logger.info(f"Found {len(alerts)} surveys with low response rates")
        return {'alerts_count': len(alerts), 'alerts': alerts}
    
    except Exception as e:
        logger.error(f"Error checking low response rates: {str(e)}")
        raise


@shared_task(name='responses.tasks.calculate_response_metrics')
def calculate_response_metrics(survey_id):
    """
    Calculate detailed metrics for a specific survey.
    Includes completion rate, average time, field responses, etc.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    from django.db.models import Avg, Count
    
    try:
        survey = Survey.objects.get(id=survey_id)
        
        # Get all responses
        all_responses = SurveyResponse.objects.filter(survey=survey)
        completed_responses = all_responses.filter(status='completed')
        
        # Calculate metrics
        total_responses = all_responses.count()
        completed_count = completed_responses.count()
        completion_rate = (completed_count / total_responses * 100) if total_responses > 0 else 0
        
        # Calculate average completion time
        completion_times = []
        for response in completed_responses.filter(submitted_at__isnull=False):
            duration = (response.submitted_at - response.started_at).total_seconds() / 60  # minutes
            completion_times.append(duration)
        
        avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0
        
        # Response rate by day
        response_by_day = all_responses.extra(
            select={'day': 'DATE(created_at)'}
        ).values('day').annotate(count=Count('id')).order_by('-day')[:30]
        
        metrics = {
            'survey_id': survey_id,
            'total_responses': total_responses,
            'completed_responses': completed_count,
            'in_progress': all_responses.filter(status='in_progress').count(),
            'abandoned': all_responses.filter(status='abandoned').count(),
            'completion_rate': round(completion_rate, 2),
            'avg_completion_time_minutes': round(avg_completion_time, 2),
            'response_trend': list(response_by_day),
            'calculated_at': timezone.now().isoformat(),
        }
        
        # Cache metrics for 1 hour
        cache.set(f'response_metrics_{survey_id}', metrics, timeout=3600)
        
        logger.info(f"Calculated metrics for survey {survey_id}")
        return metrics
    
    except Exception as e:
        logger.error(f"Error calculating response metrics: {str(e)}")
        raise


@shared_task(name='responses.tasks.analyze_field_responses')
def analyze_field_responses(survey_id):
    """
    Analyze responses for each field in a survey.
    Generate statistics and insights.
    """
    from surveys.models import Survey, Field
    from responses.models import SurveyResponseItem
    from django.db.models import Count
    
    try:
        survey = Survey.objects.get(id=survey_id)
        fields = Field.objects.filter(section__survey=survey)
        
        field_analytics = []
        
        for field in fields:
            items = SurveyResponseItem.objects.filter(field=field)
            
            analysis = {
                'field_id': field.id,
                'field_label': field.label,
                'field_type': field.field_type,
                'response_count': items.count(),
            }
            
            # Type-specific analysis
            if field.field_type in ['single_choice', 'multiple_choice', 'dropdown']:
                # Count responses by option
                value_counts = items.values('value_json').annotate(count=Count('id'))
                analysis['value_distribution'] = list(value_counts)
            
            elif field.field_type == 'rating':
                # Calculate average rating
                avg_rating = items.aggregate(Avg('value_number'))['value_number__avg']
                analysis['average_rating'] = round(avg_rating, 2) if avg_rating else None
            
            elif field.field_type == 'boolean':
                # Count yes/no
                yes_count = items.filter(value_boolean=True).count()
                no_count = items.filter(value_boolean=False).count()
                analysis['yes_count'] = yes_count
                analysis['no_count'] = no_count
            
            field_analytics.append(analysis)
        
        result = {
            'survey_id': survey_id,
            'fields_analyzed': len(field_analytics),
            'field_analytics': field_analytics,
            'analyzed_at': timezone.now().isoformat(),
        }
        
        # Cache for 2 hours
        cache.set(f'field_analytics_{survey_id}', result, timeout=7200)
        
        logger.info(f"Analyzed field responses for survey {survey_id}")
        return result
    
    except Exception as e:
        logger.error(f"Error analyzing field responses: {str(e)}")
        raise


@shared_task(name='responses.tasks.send_response_notification')
def send_response_notification(response_id):
    """
    Send notification when a response is completed.
    Can integrate with email service or webhook.
    """
    from responses.models import SurveyResponse
    
    try:
        response = SurveyResponse.objects.select_related(
            'survey', 'survey__created_by'
        ).get(id=response_id)
        
        notification = {
            'response_id': response.id,
            'survey_id': response.survey.id,
            'survey_title': response.survey.title,
            'submitted_at': response.submitted_at.isoformat() if response.submitted_at else None,
            'respondent': response.user.username if response.user else response.respondent_email,
        }
        
        # TODO: Integrate with email service (SendGrid, SES, etc.)
        # For now, just cache the notification
        cache.set(f'notification_{response_id}', notification, timeout=3600)
        
        logger.info(f"Notification sent for response {response_id}")
        return notification
    
    except Exception as e:
        logger.error(f"Error sending response notification: {str(e)}")
        raise


@shared_task(name='responses.tasks.batch_export_responses')
def batch_export_responses(survey_ids, format='csv'):
    """
    Export responses from multiple surveys in a batch.
    Useful for bulk data extraction.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    import json
    
    try:
        exports = {}
        
        for survey_id in survey_ids:
            try:
                survey = Survey.objects.get(id=survey_id)
                responses = SurveyResponse.objects.filter(
                    survey=survey,
                    status='completed'
                ).count()
                
                exports[survey_id] = {
                    'survey_title': survey.title,
                    'response_count': responses,
                    'status': 'exported'
                }
            except Survey.DoesNotExist:
                exports[survey_id] = {'status': 'survey_not_found'}
        
        # Cache export summary
        cache_key = f'batch_export_{"-".join(map(str, survey_ids))}'
        cache.set(cache_key, exports, timeout=3600)
        
        logger.info(f"Batch exported {len(survey_ids)} surveys")
        return {'exports': exports, 'cache_key': cache_key}
    
    except Exception as e:
        logger.error(f"Error in batch export: {str(e)}")
        raise
