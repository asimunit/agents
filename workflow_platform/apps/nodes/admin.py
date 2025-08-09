"""
Nodes Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import (
    NodeType, NodeTypeCategory, CustomNodeType,
    NodeCredential, NodeExecutionLog
)


@admin.register(NodeTypeCategory)
class NodeTypeCategoryAdmin(admin.ModelAdmin):
    """Node type category admin"""

    list_display = ['name', 'description', 'icon', 'color', 'node_count']
    search_fields = ['name', 'description']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            node_count=Count('node_types')
        )

    def node_count(self, obj):
        """Display node type count in category"""
        count = obj.node_count
        if count > 0:
            url = reverse('admin:nodes_nodetype_changelist')
            return format_html(
                '<a href="{}?category={}">{}</a>',
                url, obj.id, count
            )
        return count

    node_count.short_description = 'Node Types'
    node_count.admin_order_field = 'node_count'


@admin.register(NodeType)
class NodeTypeAdmin(admin.ModelAdmin):
    """Node type admin"""

    list_display = [
        'name', 'display_name', 'category', 'version', 'is_active',
        'usage_count', 'is_official', 'created_at'
    ]

    list_filter = [
        'category', 'is_active', 'is_official', 'created_at'
    ]

    search_fields = ['name', 'display_name', 'description']

    readonly_fields = ['created_at', 'updated_at', 'usage_statistics']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name', 'display_name', 'description', 'category',
                'icon', 'color', 'version'
            )
        }),
        ('Configuration', {
            'fields': (
                'input_schema', 'output_schema', 'execution_type',
                'timeout_seconds', 'max_retries'
            ),
            'classes': ('collapse',)
        }),
        ('Code & Implementation', {
            'fields': ('code', 'requirements', 'documentation'),
            'classes': ('collapse',)
        }),
        ('Status & Metadata', {
            'fields': (
                'is_active', 'is_official', 'tags', 'created_at',
                'updated_at', 'usage_statistics'
            ),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')

    def usage_count(self, obj):
        """Display usage count"""
        # This would need to be calculated from workflow usage
        return "N/A"  # Placeholder

    usage_count.short_description = 'Usage Count'

    def usage_statistics(self, obj):
        """Display usage statistics"""
        try:
            # Calculate statistics from node execution logs
            logs = NodeExecutionLog.objects.filter(node_type=obj.name)
            total = logs.count()
            successful = logs.filter(status='success').count()

            if total > 0:
                success_rate = (successful / total) * 100
                return format_html(
                    'Total: {}<br>Success Rate: {:.1f}%',
                    total, success_rate
                )
            return "No usage data"
        except Exception:
            return "Error calculating stats"

    usage_statistics.short_description = 'Usage Statistics'


@admin.register(CustomNodeType)
class CustomNodeTypeAdmin(admin.ModelAdmin):
    """Custom node type admin"""

    list_display = [
        'name', 'display_name', 'organization', 'visibility',
        'is_active', 'created_by', 'created_at'
    ]

    list_filter = [
        'visibility', 'is_active', 'created_at', 'organization'
    ]

    search_fields = [
        'name', 'display_name', 'description', 'organization__name'
    ]

    readonly_fields = ['created_at', 'updated_at', 'share_count']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name', 'display_name', 'description', 'organization',
                'icon', 'color', 'version'
            )
        }),
        ('Configuration', {
            'fields': (
                'input_schema', 'output_schema', 'execution_type',
                'timeout_seconds', 'max_retries'
            ),
            'classes': ('collapse',)
        }),
        ('Implementation', {
            'fields': ('code', 'requirements', 'documentation'),
            'classes': ('collapse',)
        }),
        ('Sharing & Visibility', {
            'fields': (
                'visibility', 'is_active', 'shared_with_orgs', 'share_count'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'created_by'
        )

    def share_count(self, obj):
        """Count of organizations this node is shared with"""
        return obj.shared_with_orgs.count()

    share_count.short_description = 'Shared With'


@admin.register(NodeCredential)
class NodeCredentialAdmin(admin.ModelAdmin):
    """Node credential admin"""

    list_display = [
        'name', 'organization', 'credential_type', 'node_types_display',
        'is_active', 'created_by', 'created_at'
    ]

    list_filter = [
        'credential_type', 'is_active', 'created_at', 'organization'
    ]

    search_fields = [
        'name', 'description', 'organization__name', 'created_by__username'
    ]

    readonly_fields = ['created_at', 'updated_at', 'last_used_at']

    fieldsets = (
        ('Credential Information', {
            'fields': (
                'name', 'description', 'organization', 'credential_type'
            )
        }),
        ('Configuration', {
            'fields': ('credential_data', 'node_types', 'is_active'),
            'classes': ('collapse',)
        }),
        ('Usage Tracking', {
            'fields': ('last_used_at',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'created_by'
        )

    def node_types_display(self, obj):
        """Display applicable node types"""
        types = obj.node_types
        if types and len(types) > 0:
            if len(types) <= 3:
                return ', '.join(types)
            else:
                return f"{', '.join(types[:3])} +{len(types) - 3} more"
        return "All types"

    node_types_display.short_description = 'Node Types'


@admin.register(NodeExecutionLog)
class NodeExecutionLogAdmin(admin.ModelAdmin):
    """Node execution log admin"""

    list_display = [
        'node_id', 'node_type', 'workflow_execution', 'status',
        'execution_time_display', 'started_at'
    ]

    list_filter = [
        'status', 'node_type', 'started_at', 'is_retry'
    ]

    search_fields = [
        'node_id', 'node_type', 'workflow_execution__execution_id'
    ]

    readonly_fields = [
        'started_at', 'completed_at', 'execution_time', 'retry_count'
    ]

    fieldsets = (
        ('Execution Information', {
            'fields': (
                'workflow_execution', 'node_id', 'node_type', 'status'
            )
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'execution_time')
        }),
        ('Input/Output', {
            'fields': ('input_data', 'output_data'),
            'classes': ('collapse',)
        }),
        ('Error Handling', {
            'fields': ('error_message', 'error_details', 'is_retry', 'retry_count'),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('memory_usage_mb', 'cpu_usage_percent'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('workflow_execution')

    def execution_time_display(self, obj):
        """Display execution time with formatting"""
        if obj.execution_time:
            seconds = obj.execution_time.total_seconds()
            if seconds < 1:
                return f"{seconds * 1000:.0f}ms"
            elif seconds < 60:
                return f"{seconds:.2f}s"
            else:
                minutes = seconds // 60
                seconds = seconds % 60
                return f"{int(minutes)}m {seconds:.1f}s"
        return "-"

    execution_time_display.short_description = 'Duration'
    execution_time_display.admin_order_field = 'execution_time'

    # Limit the number of records shown by default for performance
    def changelist_view(self, request, extra_context=None):
        # Only show recent logs by default
        if not request.GET.get('started_at__gte'):
            from django.utils import timezone
            from datetime import timedelta
            seven_days_ago = timezone.now() - timedelta(days=7)
            request.GET = request.GET.copy()
            request.GET['started_at__gte'] = seven_days_ago.strftime('%Y-%m-%d')

        return super().changelist_view(request, extra_context)