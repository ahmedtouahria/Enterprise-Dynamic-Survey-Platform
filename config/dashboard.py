"""
Admin Dashboard Configuration

Custom dashboard for the Unfold admin interface.
"""

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _


def dashboard_callback(request, context):
    """
    Dashboard callback for Unfold admin.
    Returns statistics and metrics for the dashboard.
    """
    from surveys.models import Survey
    from responses.models import SurveyResponse
    from rbac.models import Role, UserRole
    from audits.models import AuditLog
    from django.contrib.auth.models import User
    
    # Survey statistics
    total_surveys = Survey.objects.count()
    published_surveys = Survey.objects.filter(status='published').count()
    draft_surveys = Survey.objects.filter(status='draft').count()
    
    # Response statistics
    total_responses = SurveyResponse.objects.count()
    completed_responses = SurveyResponse.objects.filter(status='completed').count()
    in_progress_responses = SurveyResponse.objects.filter(status='in_progress').count()
    
    # User statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # Recent activity
    recent_surveys = Survey.objects.order_by('-created_at')[:5]
    recent_responses = SurveyResponse.objects.order_by('-created_at')[:5]
    recent_logs = AuditLog.objects.order_by('-created_at')[:10]
    
    # Add data to context
    context.update({
        "total_surveys": total_surveys,
        "published_surveys": published_surveys,
        "draft_surveys": draft_surveys,
        "total_responses": total_responses,
        "completed_responses": completed_responses,
        "in_progress_responses": in_progress_responses,
        "total_users": total_users,
        "active_users": active_users,
        "recent_surveys": recent_surveys,
        "recent_responses": recent_responses,
        "recent_logs": recent_logs,
    })
    
    return context
