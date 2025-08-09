"""
Workflows Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Avg
from django.utils import timezone
from .models import (
    Workflow, WorkflowExecution, WorkflowTemplate,
    WorkflowComment, WorkflowShare, WorkflowCategory
)


class WorkflowExecutionInline(admin.TabularInline):
    """Inline for workflow executions"""
    model = WorkflowExecution
    extra = 0
    fields = ['status', 'started_at', 'completed_at', 'execution_time', 'triggered_by']
    readonly_fields = ['started_at', 'completed_at', 'execution_time']
    can_delete = False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('triggered_by').order_by('-started_at')[:10]


class WorkflowShareInline(admin.TabularInline):
    """Inline for workflow shares"""
    model = WorkflowShare
    extra = 0
    fields = ['shared_with', 'permission', 'shared_by', 'shared_at']
    readonly_fields = ['shared_at']


class WorkflowCommentInline(admin.TabularInline):
    """Inline for workflow comments"""
    model = WorkflowComment
    extra = 0
    fields = ['author', 'content', 'node_id', 'created_at']
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author').order_by('-created_at')[:5]


@admin.register(WorkflowCategory)
class WorkflowCategoryAdmin(admin.ModelAdmin):
    """Workflow category admin"""

    list_display = ['name', 'description', 'icon', 'color', 'workflow_count']
    search_fields = ['name', 'description']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            workflow_count=Count('workflows')
        )

    def workflow_count(self, obj):
        """Display workflow count in category"""
        count = obj.workflow_count
        if count > 0:
            url = reverse('admin:workflows_workflow_changelist')
            return format_html(
                '<a href="{}?category={}">{}</a>',
                url, obj.id, count
            )
        return count

    workflow_count.short_description = 'Workflows'
    workflow_count.admin_order_field = 'workflow_count'


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    """Workflow admin"""

    list_display = [
        'name', 'organization', 'category', 'status', 'version',
        'execution_count', 'success_rate_display', 'created_by', 'created_at'
    ]

    list_filter = [
        'status', 'trigger_type', 'is_public', 'is_template',
        'category', 'created_at', 'organization'
    ]

    search_fields = ['name', 'description', 'created_by__username', 'organization__name']

    readonly_fields = [
        'created_at', 'updated_at', 'total_executions', 'successful_executions',
        'failed_executions', 'last_executed_at', 'average_execution_time', 'success_rate'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'organization', 'category', 'tags')
        }),
        ('Configuration', {
            'fields': (
                'status', 'trigger_type', 'version', 'is_latest_version',
                'is_public', 'is_template'
            )
        }),
        ('Workflow Definition', {
            'fields': ('nodes', 'connections', 'variables'),
            'classes': ('collapse',)
        }),
        ('Execution Settings', {
            'fields': (
                'execution_timeout', 'max_retries', 'retry_delay',
                'parallel_execution', 'schedule_expression', 'schedule_timezone'
            ),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': (
                'total_executions', 'successful_executions', 'failed_executions',
                'last_executed_at', 'average_execution_time', 'success_rate'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [WorkflowExecutionInline, WorkflowShareInline, WorkflowCommentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'category', 'created_by', 'updated_by'
        ).annotate(
            execution_count=Count('executions')
        )

    def execution_count(self, obj):
        """Display execution count"""
        count = obj.execution_count
        if count > 0:
            url = reverse('admin:workflows_workflowexecution_changelist')
            return format_html(
                '<a href="{}?workflow={}">{}</a>',
                url, obj.id, count
            )
        return count

    execution_count.short_description = 'Executions'
    execution_count.admin_order_field = 'execution_count'

    def success_rate_display(self, obj):
        """Display success rate with color coding"""
        rate = obj.success_rate
        if rate >= 90:
            color = 'green'
        elif rate >= 70:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )

    success_rate_display.short_description = 'Success Rate'
    success_rate_display.admin_order_field = 'success_rate'


@admin.register(WorkflowExecution)
class WorkflowExecutionAdmin(admin.ModelAdmin):
    """Workflow execution admin"""

    list_display = [
        'id', 'workflow', 'status', 'trigger_source',  # Changed from 'trigger_type'
        'started_at', 'completed_at', 'triggered_by'
    ]

    list_filter = ['status', 'trigger_source', 'started_at']  # Changed from 'trigger_type'

    search_fields = ['workflow__name', 'triggered_by__username']

    readonly_fields = ['started_at', 'completed_at', 'execution_time']  # Removed non-existent field

    fieldsets = (
        ('Execution Information', {
            'fields': ('workflow', 'status', 'trigger_source', 'triggered_by')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'execution_time')
        }),
        ('Data', {
            'fields': ('input_data', 'output_data'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        })
    )

    def trigger_type(self, obj):
        """Display trigger type"""
        return obj.trigger_source

    trigger_type.short_description = 'Trigger Type'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'workflow', 'triggered_by'
        )

    def execution_time_display(self, obj):
        """Display execution time with formatting"""
        if obj.execution_time:
            seconds = obj.execution_time.total_seconds()
            if seconds < 60:
                return f"{seconds:.2f}s"
            else:
                minutes = seconds // 60
                seconds = seconds % 60
                return f"{int(minutes)}m {seconds:.1f}s"
        return "-"

    execution_time_display.short_description = 'Duration'
    execution_time_display.admin_order_field = 'execution_time'

    def node_executions_count(self, obj):
        """Count of node executions"""
        return len(obj.context_data.get('node_executions', []))

    node_executions_count.short_description = 'Node Executions'


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    """Workflow template admin"""

    list_display = [
        'title', 'workflow', 'difficulty', 'industry',  # Changed from 'name', 'category', 'use_count', 'created_by'
        'usage_count', 'is_featured', 'published_at'
    ]

    list_filter = ['difficulty', 'industry', 'is_featured', 'is_official']  # Changed from 'category'

    search_fields = ['title', 'short_description', 'industry']

    readonly_fields = ['usage_count', 'rating', 'rating_count', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('workflow', 'title', 'short_description', 'long_description')
        }),
        ('Categorization', {
            'fields': ('difficulty', 'industry', 'use_case')
        }),
        ('Media', {
            'fields': ('thumbnail', 'screenshots')
        }),
        ('Statistics', {
            'fields': ('usage_count', 'rating', 'rating_count'),
            'classes': ('collapse',)
        }),
        ('Publishing', {
            'fields': ('is_featured', 'is_official', 'published_at')
        }),
        ('Requirements', {
            'fields': ('required_integrations', 'required_plan')
        })
    )

    def name(self, obj):
        """Template name"""
        return obj.title

    name.short_description = 'Name'

    def category(self, obj):
        """Template category"""
        return obj.industry

    category.short_description = 'Category'

    def created_by(self, obj):
        """Template creator"""
        return obj.workflow.created_by if obj.workflow else None

    created_by.short_description = 'Created By'

    def rating_display(self, obj):
        """Display rating with stars"""
        if obj.rating:
            stars = '★' * int(obj.rating) + '☆' * (5 - int(obj.rating))
            return format_html(
                '<span title="{:.1f}/5">{}</span>',
                obj.rating, stars
            )
        return "No rating"

    rating_display.short_description = 'Rating'
    rating_display.admin_order_field = 'rating'


@admin.register(WorkflowShare)
class WorkflowShareAdmin(admin.ModelAdmin):
    """Workflow sharing admin"""

    list_display = [
        'workflow', 'shared_with', 'permission', 'shared_by', 'shared_at'
    ]

    list_filter = ['permission', 'shared_at']

    search_fields = [
        'workflow__name', 'shared_with__username', 'shared_by__username'
    ]

    readonly_fields = ['shared_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'workflow', 'shared_with', 'shared_by'
        )


@admin.register(WorkflowComment)
class WorkflowCommentAdmin(admin.ModelAdmin):
    """Workflow comment admin"""

    list_display = [
        'workflow', 'author', 'content_preview', 'node_id', 'created_at'
    ]

    list_filter = ['created_at', 'workflow__organization']

    search_fields = [
        'workflow__name', 'author__username', 'content'
    ]

    readonly_fields = ['created_at', 'updated_at']

    def content_preview(self, obj):
        """Show preview of comment content"""
        if len(obj.content) > 50:
            return obj.content[:50] + "..."
        return obj.content

    content_preview.short_description = 'Content'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'workflow', 'author'
        )