"""
Executions Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Avg
from django.utils import timezone
from .models import (
    ExecutionQueue, ExecutionHistory, ExecutionAlert,
    ExecutionResource, ExecutionSchedule
)


@admin.register(ExecutionQueue)
class ExecutionQueueAdmin(admin.ModelAdmin):
    """Execution queue admin"""

    list_display = [
        'execution_id', 'workflow', 'status', 'priority',
        'attempt_count', 'scheduled_at', 'created_at'
    ]

    list_filter = [
        'status', 'priority', 'trigger_type', 'created_at', 'scheduled_at'
    ]

    search_fields = [
        'execution_id', 'workflow__name', 'triggered_by__username'
    ]

    readonly_fields = [
        'execution_id', 'created_at', 'started_at', 'completed_at'
    ]

    fieldsets = (
        ('Execution Information', {
            'fields': (
                'workflow', 'execution_id', 'status', 'priority'
            )
        }),
        ('Trigger Details', {
            'fields': (
                'trigger_type', 'trigger_data', 'triggered_by'
            )
        }),
        ('Scheduling', {
            'fields': (
                'scheduled_at', 'max_attempts', 'attempt_count'
            )
        }),
        ('Data', {
            'fields': ('input_data', 'variables'),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('created_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        })
    )

    actions = ['retry_failed_executions', 'cancel_pending_executions']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'workflow', 'triggered_by'
        )

    def retry_failed_executions(self, request, queryset):
        """Retry failed executions"""
        failed_executions = queryset.filter(status='failed')
        retryable = [exec for exec in failed_executions if exec.can_retry()]

        for execution in retryable:
            execution.status = 'pending'
            execution.error_message = ''
            execution.error_details = {}
            execution.save()

        self.message_user(
            request,
            f"Retried {len(retryable)} executions."
        )

    retry_failed_executions.short_description = "Retry failed executions"

    def cancel_pending_executions(self, request, queryset):
        """Cancel pending executions"""
        pending_executions = queryset.filter(status='pending')
        count = pending_executions.update(status='cancelled')

        self.message_user(
            request,
            f"Cancelled {count} pending executions."
        )

    cancel_pending_executions.short_description = "Cancel pending executions"


@admin.register(ExecutionHistory)
class ExecutionHistoryAdmin(admin.ModelAdmin):
    """Execution history admin"""

    list_display = [
        'execution_id', 'workflow', 'status', 'duration_display',
        'nodes_executed', 'trigger_type', 'started_at'
    ]

    list_filter = [
        'status', 'trigger_type', 'started_at', 'organization'
    ]

    search_fields = [
        'execution_id', 'workflow__name', 'triggered_by__username'
    ]

    readonly_fields = [
        'execution_id', 'started_at', 'completed_at', 'execution_time',
        'created_at', 'performance_summary'
    ]

    fieldsets = (
        ('Execution Information', {
            'fields': (
                'organization', 'workflow', 'execution_id', 'status'
            )
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'execution_time')
        }),
        ('Performance', {
            'fields': (
                'nodes_executed', 'nodes_failed', 'memory_peak_mb',
                'performance_summary'
            ),
            'classes': ('collapse',)
        }),
        ('Trigger Information', {
            'fields': ('trigger_type', 'triggered_by'),
            'classes': ('collapse',)
        }),
        ('Data Metrics', {
            'fields': ('input_size_bytes', 'output_size_bytes'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_type', 'error_message'),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'started_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'workflow', 'triggered_by'
        )

    def duration_display(self, obj):
        """Display execution duration with formatting"""
        seconds = obj.duration_seconds
        if seconds < 60:
            return f"{seconds:.2f}s"
        else:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{int(minutes)}m {seconds:.1f}s"

    duration_display.short_description = 'Duration'
    duration_display.admin_order_field = 'execution_time'

    def performance_summary(self, obj):
        """Display performance summary"""
        summary = []
        if obj.nodes_executed:
            summary.append(f"Nodes: {obj.nodes_executed}")
        if obj.nodes_failed:
            summary.append(f"Failed: {obj.nodes_failed}")
        if obj.memory_peak_mb:
            summary.append(f"Memory: {obj.memory_peak_mb:.1f}MB")

        return " | ".join(summary) if summary else "No data"

    performance_summary.short_description = 'Performance Summary'


@admin.register(ExecutionAlert)
class ExecutionAlertAdmin(admin.ModelAdmin):
    """Execution alert admin"""

    list_display = [
        'title', 'workflow', 'alert_type', 'severity',
        'status', 'created_at', 'acknowledged_by'
    ]

    list_filter = [
        'alert_type', 'severity', 'status', 'created_at', 'organization'
    ]

    search_fields = [
        'title', 'message', 'workflow__name', 'execution_id'
    ]

    readonly_fields = [
        'created_at', 'updated_at', 'acknowledged_at', 'resolved_at'
    ]

    fieldsets = (
        ('Alert Information', {
            'fields': (
                'organization', 'workflow', 'alert_type', 'severity', 'status'
            )
        }),
        ('Details', {
            'fields': ('title', 'message', 'execution_id')
        }),
        ('Recipients', {
            'fields': ('notified_users', 'notification_sent'),
            'classes': ('collapse',)
        }),
        ('Resolution', {
            'fields': (
                'acknowledged_by', 'acknowledged_at', 'resolved_at'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    actions = ['mark_acknowledged', 'mark_resolved']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'workflow', 'acknowledged_by'
        )

    def mark_acknowledged(self, request, queryset):
        """Mark alerts as acknowledged"""
        active_alerts = queryset.filter(status='active')
        count = 0

        for alert in active_alerts:
            alert.acknowledge(request.user)
            count += 1

        self.message_user(
            request,
            f"Acknowledged {count} alerts."
        )

    mark_acknowledged.short_description = "Mark as acknowledged"

    def mark_resolved(self, request, queryset):
        """Mark alerts as resolved"""
        unresolved_alerts = queryset.exclude(status='resolved')
        count = 0

        for alert in unresolved_alerts:
            alert.resolve()
            count += 1

        self.message_user(
            request,
            f"Resolved {count} alerts."
        )

    mark_resolved.short_description = "Mark as resolved"


@admin.register(ExecutionResource)
class ExecutionResourceAdmin(admin.ModelAdmin):
    """Execution resource admin"""

    list_display = [
        'execution_id', 'organization', 'duration_display',
        'avg_cpu_display', 'avg_memory_display', 'storage_mb'
    ]

    list_filter = ['organization', 'start_time']

    search_fields = ['execution_id', 'organization__name']

    readonly_fields = [
        'created_at', 'avg_cpu_display', 'avg_memory_display'
    ]

    fieldsets = (
        ('Execution Information', {
            'fields': ('execution_id', 'organization')
        }),
        ('Timing', {
            'fields': ('start_time', 'end_time', 'duration_seconds')
        }),
        ('Resource Usage', {
            'fields': (
                'cpu_seconds', 'memory_mb_seconds', 'storage_mb', 'network_bytes'
            )
        }),
        ('Calculated Metrics', {
            'fields': ('avg_cpu_display', 'avg_memory_display'),
            'classes': ('collapse',)
        }),
        ('Detailed Breakdown', {
            'fields': ('node_resource_usage',),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'start_time'

    def duration_display(self, obj):
        """Display duration with formatting"""
        seconds = obj.duration_seconds
        if seconds < 60:
            return f"{seconds:.1f}s"
        else:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{int(minutes)}m {seconds:.1f}s"

    duration_display.short_description = 'Duration'
    duration_display.admin_order_field = 'duration_seconds'

    def avg_cpu_display(self, obj):
        """Display average CPU usage"""
        cpu = obj.average_cpu_usage
        if cpu > 0:
            return f"{cpu:.1f}%"
        return "0%"

    avg_cpu_display.short_description = 'Avg CPU'

    def avg_memory_display(self, obj):
        """Display average memory usage"""
        memory = obj.average_memory_usage
        if memory > 0:
            return f"{memory:.1f}MB"
        return "0MB"

    avg_memory_display.short_description = 'Avg Memory'


@admin.register(ExecutionSchedule)
class ExecutionScheduleAdmin(admin.ModelAdmin):
    """Execution schedule admin"""

    list_display = [
        'workflow', 'status', 'cron_expression', 'next_run_time',
        'run_count', 'failure_count', 'last_run_time'
    ]

    list_filter = ['status', 'timezone', 'created_at']

    search_fields = ['workflow__name', 'cron_expression']

    readonly_fields = [
        'next_run_time', 'last_run_time', 'run_count', 'failure_count',
        'created_at', 'updated_at', 'schedule_status'
    ]

    fieldsets = (
        ('Schedule Configuration', {
            'fields': (
                'workflow', 'cron_expression', 'timezone', 'status'
            )
        }),
        ('Execution Settings', {
            'fields': (
                'max_concurrent_executions', 'timeout_minutes'
            )
        }),
        ('Error Handling', {
            'fields': (
                'max_failures', 'failure_notification_threshold'
            ),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': (
                'next_run_time', 'last_run_time', 'run_count', 'failure_count'
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('schedule_status',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    actions = ['enable_schedules', 'disable_schedules', 'reset_failure_count']

    def schedule_status(self, obj):
        """Display schedule status with warnings"""
        status_info = []

        if obj.should_disable():
            status_info.append(
                format_html('<span style="color: red;">⚠ Too many failures</span>')
            )

        if obj.next_run_time < timezone.now():
            status_info.append(
                format_html('<span style="color: orange;">⏰ Overdue</span>')
            )

        if not status_info:
            status_info.append(
                format_html('<span style="color: green;">✓ Healthy</span>')
            )

        return format_html('<br>'.join(status_info))

    schedule_status.short_description = 'Status'

    def enable_schedules(self, request, queryset):
        """Enable selected schedules"""
        count = queryset.update(status='active')
        self.message_user(
            request,
            f"Enabled {count} schedules."
        )

    enable_schedules.short_description = "Enable schedules"

    def disable_schedules(self, request, queryset):
        """Disable selected schedules"""
        count = queryset.update(status='disabled')
        self.message_user(
            request,
            f"Disabled {count} schedules."
        )

    disable_schedules.short_description = "Disable schedules"

    def reset_failure_count(self, request, queryset):
        """Reset failure count for selected schedules"""
        count = queryset.update(failure_count=0)
        self.message_user(
            request,
            f"Reset failure count for {count} schedules."
        )

    reset_failure_count.short_description = "Reset failure count"