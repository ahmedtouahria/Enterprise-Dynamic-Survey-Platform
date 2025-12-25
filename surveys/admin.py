"""
Survey Admin Configuration

Comprehensive admin interface for survey management with:
- Inline editing for sections, fields, and options
- Custom actions and filters
- Search functionality
- Read-only fields for audit trail
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display
from .models import (
    Survey, Section, Field, FieldOption, 
    ConditionalLogic, FieldDependency
)


class SectionInline(StackedInline):
    """Inline for survey sections"""
    model = Section
    extra = 0
    fields = ['title', 'description', 'order', 'is_conditional']
    ordering = ['order']


class FieldInline(TabularInline):
    """Inline for section fields"""
    model = Field
    extra = 0
    fields = ['label', 'field_type', 'order', 'is_required', 'is_conditional', 'is_encrypted']
    ordering = ['order']


class FieldOptionInline(TabularInline):
    """Inline for field options"""
    model = FieldOption
    extra = 0
    fields = ['label', 'value', 'order', 'is_exclusive']
    ordering = ['order']


@admin.register(Survey)
class SurveyAdmin(ModelAdmin):
    """Admin for Survey model"""
    list_display = [
        'title', 'status_badge', 'version', 'is_active_version',
        'created_by', 'response_count', 'created_at'
    ]
    list_filter = [
        'status', 'is_active_version', 'allow_multiple_submissions',
        'allow_partial_submissions', 'created_at'
    ]
    search_fields = ['title', 'description', 'tenant_id']
    readonly_fields = [
        'version', 'created_at', 'updated_at', 'created_by',
        'response_count_display'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'status')
        }),
        ('Versioning', {
            'fields': ('version', 'parent_survey', 'is_active_version'),
            'classes': ['collapse']
        }),
        ('Settings', {
            'fields': (
                'allow_multiple_submissions',
                'allow_partial_submissions',
                'submission_deadline'
            )
        }),
        ('Multi-tenancy', {
            'fields': ('tenant_id', 'created_by'),
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ('metadata', 'response_count_display'),
            'classes': ['collapse']
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    inlines = [SectionInline]
    
    actions = ['publish_surveys', 'archive_surveys', 'create_new_version']
    
    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {
            'draft': 'warning',
            'published': 'success',
            'archived': 'danger'
        }
        return colors.get(obj.status, 'info')
    
    @display(description="Responses")
    def response_count(self, obj):
        return obj.responses.count()
    
    def response_count_display(self, obj):
        count = obj.responses.count()
        completed = obj.responses.filter(status='completed').count()
        in_progress = obj.responses.filter(status='in_progress').count()
        return format_html(
            '<strong>Total:</strong> {} | <strong>Completed:</strong> {} | <strong>In Progress:</strong> {}',
            count, completed, in_progress
        )
    response_count_display.short_description = 'Response Statistics'
    
    @admin.action(description='Publish selected surveys')
    def publish_surveys(self, request, queryset):
        queryset.update(status='published')
        self.message_user(request, f'{queryset.count()} surveys published successfully.')
    
    @admin.action(description='Archive selected surveys')
    def archive_surveys(self, request, queryset):
        queryset.update(status='archived')
        self.message_user(request, f'{queryset.count()} surveys archived successfully.')
    
    @admin.action(description='Create new version')
    def create_new_version(self, request, queryset):
        for survey in queryset:
            survey.create_new_version()
        self.message_user(request, f'New versions created for {queryset.count()} surveys.')


@admin.register(Section)
class SectionAdmin(ModelAdmin):
    """Admin for Section model"""
    list_display = ['title', 'survey', 'order', 'is_conditional', 'field_count']
    list_filter = ['is_conditional', 'survey__status']
    search_fields = ['title', 'description', 'survey__title']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('survey', 'title', 'description', 'order')
        }),
        ('Conditional Display', {
            'fields': ('is_conditional',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    inlines = [FieldInline]
    
    @display(description="Fields")
    def field_count(self, obj):
        return obj.fields.count()


@admin.register(Field)
class FieldAdmin(ModelAdmin):
    """Admin for Field model"""
    list_display = [
        'label', 'field_type_badge', 'section', 'order',
        'is_required', 'is_conditional', 'is_encrypted', 'option_count'
    ]
    list_filter = [
        'field_type', 'is_required', 'is_conditional',
        'is_encrypted', 'section__survey__status'
    ]
    search_fields = ['label', 'description', 'section__title']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('section', 'label', 'description', 'field_type', 'placeholder', 'order')
        }),
        ('Validation', {
            'fields': (
                'is_required', 'min_value', 'max_value',
                'min_length', 'max_length', 'regex_pattern'
            )
        }),
        ('Advanced Options', {
            'fields': ('is_conditional', 'is_encrypted', 'config'),
            'classes': ['collapse']
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    inlines = [FieldOptionInline]
    
    @display(description="Type", label=True)
    def field_type_badge(self, obj):
        return 'info'
    
    @display(description="Options")
    def option_count(self, obj):
        return obj.options.count()


@admin.register(FieldOption)
class FieldOptionAdmin(ModelAdmin):
    """Admin for FieldOption model"""
    list_display = ['label', 'value', 'field', 'order', 'is_exclusive']
    list_filter = ['is_exclusive', 'field__field_type']
    search_fields = ['label', 'value', 'field__label']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('field', 'label', 'value', 'order')
        }),
        ('Options', {
            'fields': ('is_exclusive',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )


@admin.register(ConditionalLogic)
class ConditionalLogicAdmin(ModelAdmin):
    """Admin for ConditionalLogic model"""
    list_display = [
        'trigger_field', 'action_badge', 'target_display',
        'priority', 'created_at'
    ]
    list_filter = ['action', 'priority']
    search_fields = [
        'trigger_field__label', 'target_field__label',
        'target_section__title'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Trigger', {
            'fields': ('trigger_field',)
        }),
        ('Action', {
            'fields': ('action', 'target_field', 'target_section', 'priority')
        }),
        ('Condition', {
            'fields': ('condition',),
            'description': 'Define the condition in JSON format'
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    @display(description="Action", label=True)
    def action_badge(self, obj):
        colors = {
            'show': 'success',
            'hide': 'danger',
            'require': 'warning',
            'skip_to': 'info'
        }
        return colors.get(obj.action, 'info')
    
    def target_display(self, obj):
        if obj.target_field:
            return f"Field: {obj.target_field.label}"
        elif obj.target_section:
            return f"Section: {obj.target_section.title}"
        return "N/A"
    target_display.short_description = 'Target'


@admin.register(FieldDependency)
class FieldDependencyAdmin(ModelAdmin):
    """Admin for FieldDependency model"""
    list_display = [
        'source_field', 'dependent_field',
        'dependency_type_badge', 'created_at'
    ]
    list_filter = ['dependency_type']
    search_fields = [
        'source_field__label', 'dependent_field__label'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Dependencies', {
            'fields': ('source_field', 'dependent_field', 'dependency_type')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    @display(description="Type", label=True)
    def dependency_type_badge(self, obj):
        colors = {
            'conditional_display': 'info',
            'conditional_validation': 'warning',
            'calculated_value': 'success'
        }
        return colors.get(obj.dependency_type, 'info')

