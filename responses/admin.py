"""
Response Admin Configuration

Admin interface for managing survey responses with:
- Inline field responses
- Status filtering and actions
- Export capabilities
- Response analytics
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from .models import SurveyResponse, SurveyResponseItem


class SurveyResponseItemInline(TabularInline):
    """Inline for survey response items"""
    model = SurveyResponseItem
    extra = 0
    fields = ['field', 'value_display', 'is_encrypted']
    readonly_fields = ['field', 'value_display', 'is_encrypted']
    can_delete = False
    
    def value_display(self, obj):
        value = obj.get_value()
        if isinstance(value, (list, dict)):
            return str(value)[:100]
        return str(value)[:100] if value else '-'
    value_display.short_description = 'Value'
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SurveyResponse)
class SurveyResponseAdmin(ModelAdmin):
    """Admin for SurveyResponse model"""
    list_display = [
        'id', 'survey', 'status_badge', 'respondent_display',
        'started_at', 'submitted_at', 'item_count'
    ]
    list_filter = [
        'status', 'survey__status', 'survey',
        'started_at', 'submitted_at'
    ]
    search_fields = [
        'id', 'survey__title', 'user__username',
        'respondent_email', 'resume_token'
    ]
    readonly_fields = [
        'survey', 'user', 'respondent_email', 'status',
        'ip_address', 'user_agent', 'started_at', 'submitted_at',
        'resume_token', 'tenant_id', 'created_at', 'updated_at',
        'response_summary'
    ]
    
    fieldsets = (
        ('Response Information', {
            'fields': ('survey', 'status', 'response_summary')
        }),
        ('Respondent', {
            'fields': ('user', 'respondent_email')
        }),
        ('Timestamps', {
            'fields': ('started_at', 'submitted_at')
        }),
        ('Session Info', {
            'fields': ('resume_token', 'ip_address', 'user_agent'),
            'classes': ['collapse']
        }),
        ('Multi-tenancy', {
            'fields': ('tenant_id',),
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ['collapse']
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    inlines = [SurveyResponseItemInline]
    
    actions = ['mark_completed', 'mark_abandoned']
    
    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {
            'in_progress': 'warning',
            'completed': 'success',
            'abandoned': 'danger'
        }
        return colors.get(obj.status, 'info')
    
    def respondent_display(self, obj):
        if obj.user:
            return f"{obj.user.username} (User)"
        return f"{obj.respondent_email} (Anonymous)"
    respondent_display.short_description = 'Respondent'
    
    @display(description="Items")
    def item_count(self, obj):
        return obj.items.count()
    
    def response_summary(self, obj):
        items_count = obj.items.count()
        duration = None
        if obj.submitted_at and obj.started_at:
            duration = obj.submitted_at - obj.started_at
        
        html = f'<strong>Response Items:</strong> {items_count}<br>'
        if duration:
            html += f'<strong>Completion Time:</strong> {duration}<br>'
        html += f'<strong>Survey Version:</strong> v{obj.survey.version}'
        
        return format_html(html)
    response_summary.short_description = 'Summary'
    
    @admin.action(description='Mark as completed')
    def mark_completed(self, request, queryset):
        for response in queryset:
            response.mark_completed()
        self.message_user(request, f'{queryset.count()} responses marked as completed.')
    
    @admin.action(description='Mark as abandoned')
    def mark_abandoned(self, request, queryset):
        queryset.update(status='abandoned')
        self.message_user(request, f'{queryset.count()} responses marked as abandoned.')


@admin.register(SurveyResponseItem)
class SurveyResponseItemAdmin(ModelAdmin):
    """Admin for SurveyResponseItem model"""
    list_display = [
        'response_id', 'field', 'value_preview',
        'is_encrypted', 'created_at'
    ]
    list_filter = ['is_encrypted', 'field__field_type', 'created_at']
    search_fields = [
        'response__id', 'field__label',
        'value_text', 'response__survey__title'
    ]
    readonly_fields = [
        'response', 'field', 'value_text', 'value_number',
        'value_boolean', 'value_date', 'value_datetime',
        'value_json', 'is_encrypted', 'file_url',
        'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Response Information', {
            'fields': ('response', 'field')
        }),
        ('Values', {
            'fields': (
                'value_text', 'value_number', 'value_boolean',
                'value_date', 'value_datetime', 'value_json',
                'file_url'
            )
        }),
        ('Security', {
            'fields': ('is_encrypted',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    def response_id(self, obj):
        return obj.response.id
    response_id.short_description = 'Response ID'
    
    def value_preview(self, obj):
        value = obj.get_value()
        if isinstance(value, (list, dict)):
            return str(value)[:50] + '...'
        return str(value)[:50] if value else '-'
    value_preview.short_description = 'Value'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Responses are immutable once submitted
        if obj and obj.response.status == 'completed':
            return False
        return True

