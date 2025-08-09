"""
Analytics Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Avg
from django.utils import timezone
from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsReport,
    AnalyticsMetric, UsageAnalytics, PerformanceMetrics, AnalyticsAlert
)


class AnalyticsWidgetInline(admin.TabularInline):
    """Inline for dashboard widgets"""
    model = AnalyticsWidget
    extra = 0
    fields = ['title', 'widget_type', 'chart_type', 'position_x', 'position_y', 'is_active']
    readonly_fields = []


@admin.register(AnalyticsDashboard)
class AnalyticsDashboardAdmin(admin.ModelAdmin):
    """Analytics dashboard admin"""

    list_display = [
        'name', 'organization', 'dashboard_type', 'widget_count',
        'is_public', 'is_active', 'created_by', 'created_at'
    ]

    list_filter = [
        'dashboard_type', 'is_public', 'is_active', 'created_at', 'organization'
    ]

    search_fields = [
        'name', 'description', 'organization__name', 'created_by__username'
    ]

    readonly_fields = ['created_at', 'updated_at', 'widget_summary']

    fieldsets = (
        ('Dashboard Information', {
            'fields': (
                'name', 'description', 'organization', 'dashboard_type'
            )
        }),
        ('Configuration', {
            'fields': ('layout', 'filters', 'refresh_interval'),
            'classes': ('collapse',)
        }),
        ('Sharing & Permissions', {
            'fields': ('is_public', 'shared_with_users'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Widget Summary', {
            'fields': ('widget_summary',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [AnalyticsWidgetInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'created_by'
        ).annotate(
            widget_count=Count('widgets')
        )

    def widget_count(self, obj):
        """Display widget count"""
        count = obj.widget_count
        if count > 0:
            url = reverse('admin:analytics_analyticswidget_changelist')
            return format_html(
                '<a href="{}?dashboard={}">{}</a>',
                url, obj.id, count
            )
        return count

    widget_count.short_description = 'Widgets'
    widget_count.admin_order_field = 'widget_count'

    def widget_summary(self, obj):
        """Display widget type summary"""
        widgets = obj.widgets.all()
        if not widgets:
            return "No widgets"

        widget_types = {}
        for widget in widgets:
            widget_types[widget.widget_type] = widget_types.get(widget.widget_type, 0) + 1

        summary = []
        for widget_type, count in widget_types.items():
            summary.append(f"{widget_type.title()}: {count}")

        return " | ".join(summary)

    widget_summary.short_description = 'Widget Summary'


@admin.register(AnalyticsWidget)
class AnalyticsWidgetAdmin(admin.ModelAdmin):
    """Analytics widget admin"""

    list_display = [
        'title', 'dashboard', 'widget_type', 'chart_type',
        'data_source', 'auto_refresh', 'is_active', 'created_at'
    ]

    list_filter = [
        'widget_type', 'chart_type', 'data_source', 'auto_refresh',
        'is_active', 'created_at'
    ]

    search_fields = [
        'title', 'description', 'dashboard__name'
    ]

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Widget Information', {
            'fields': (
                'dashboard', 'title', 'description', 'widget_type', 'chart_type'
            )
        }),
        ('Data Configuration', {
            'fields': ('data_source', 'query_config'),
            'classes': ('collapse',)
        }),
        ('Display Configuration', {
            'fields': ('display_config', 'size_config'),
            'classes': ('collapse',)
        }),
        ('Position & Size', {
            'fields': (
                'position_x', 'position_y', 'width', 'height'
            )
        }),
        ('Refresh Settings', {
            'fields': ('auto_refresh', 'refresh_interval'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('dashboard')


@admin.register(AnalyticsReport)
class AnalyticsReportAdmin(admin.ModelAdmin):
    """Analytics report admin"""

    list_display = [
        'name', 'organization', 'report_type', 'delivery_method',
        'is_active', 'last_generated_at', 'next_generation_at', 'created_by'
    ]

    list_filter = [
        'report_type', 'delivery_method', 'is_active',
        'created_at', 'organization'
    ]

    search_fields = [
        'name', 'description', 'organization__name', 'created_by__username'
    ]

    readonly_fields = [
        'last_generated_at', 'created_at', 'updated_at', 'recipients_display'
    ]

    fieldsets = (
        ('Report Information', {
            'fields': (
                'name', 'description', 'organization', 'report_type'
            )
        }),
        ('Configuration', {
            'fields': ('report_config', 'filters'),
            'classes': ('collapse',)
        }),
        ('Scheduling', {
            'fields': ('schedule_expression', 'timezone', 'next_generation_at')
        }),
        ('Delivery', {
            'fields': (
                'delivery_method', 'recipients', 'recipients_display', 'delivery_config'
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'last_generated_at')
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

    def recipients_display(self, obj):
        """Display recipients in a readable format"""
        if obj.recipients:
            if len(obj.recipients) <= 3:
                return ", ".join(obj.recipients)
            else:
                return f"{', '.join(obj.recipients[:3])} +{len(obj.recipients) - 3} more"
        return "No recipients"

    recipients_display.short_description = 'Recipients'


@admin.register(AnalyticsMetric)
class AnalyticsMetricAdmin(admin.ModelAdmin):
    """Analytics metric admin"""

    list_display = [
        'name', 'organization', 'metric_type', 'category',
        'value_display', 'aggregation_period', 'period_start', 'calculated_at'
    ]

    list_filter = [
        'metric_type', 'category', 'aggregation_period',
        'calculated_at', 'organization'
    ]

    search_fields = [
        'name', 'category', 'organization__name'
    ]

    readonly_fields = ['calculated_at']

    fieldsets = (
        ('Metric Information', {
            'fields': (
                'organization', 'name', 'metric_type', 'category'
            )
        }),
        ('Value', {
            'fields': ('value', 'unit')
        }),
        ('Aggregation', {
            'fields': (
                'aggregation_period', 'period_start', 'period_end'
            )
        }),
        ('Context', {
            'fields': ('workflow', 'filters', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('calculated_at',),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'period_start'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'workflow'
        )

    def value_display(self, obj):
        """Display value with unit"""
        if obj.unit:
            return f"{obj.value} {obj.unit}"
        return str(obj.value)

    value_display.short_description = 'Value'
    value_display.admin_order_field = 'value'


@admin.register(UsageAnalytics)
class UsageAnalyticsAdmin(admin.ModelAdmin):
    """Usage analytics admin"""

    list_display = [
        'organization', 'date', 'active_users', 'total_executions',
        'success_rate_display', 'total_compute_hours', 'api_calls_count'
    ]

    list_filter = ['date', 'organization']

    search_fields = ['organization__name']

    readonly_fields = ['created_at', 'success_rate_display']

    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'date')
        }),
        ('User Metrics', {
            'fields': ('active_users', 'new_users', 'total_users')
        }),
        ('Workflow Metrics', {
            'fields': (
                'workflows_created', 'workflows_executed', 'total_workflows'
            )
        }),
        ('Execution Metrics', {
            'fields': (
                'total_executions', 'successful_executions', 'failed_executions',
                'average_execution_time', 'success_rate_display'
            )
        }),
        ('Resource Usage', {
            'fields': (
                'total_compute_hours', 'total_storage_gb', 'api_calls_count'
            ),
            'classes': ('collapse',)
        }),
        ('Feature Usage', {
            'fields': ('feature_usage',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'date'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('organization')

    def success_rate_display(self, obj):
        """Display success rate with color coding"""
        rate = obj.success_rate
        if rate >= 95:
            color = 'green'
        elif rate >= 80:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )

    success_rate_display.short_description = 'Success Rate'


@admin.register(PerformanceMetrics)
class PerformanceMetricsAdmin(admin.ModelAdmin):
    """Performance metrics admin"""

    list_display = [
        'organization', 'workflow', 'period_start', 'avg_execution_time_display',
        'executions_per_hour', 'error_rate_display', 'reliability_score'
    ]

    list_filter = ['organization', 'period_start', 'workflow']

    search_fields = ['organization__name', 'workflow__name']

    readonly_fields = ['calculated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'workflow', 'period_start', 'period_end')
        }),
        ('Execution Performance', {
            'fields': (
                'avg_execution_time', 'min_execution_time', 'max_execution_time',
                'p95_execution_time'
            )
        }),
        ('Throughput', {
            'fields': ('executions_per_hour', 'peak_concurrent_executions'),
            'classes': ('collapse',)
        }),
        ('Resource Utilization', {
            'fields': (
                'avg_cpu_usage', 'avg_memory_usage', 'peak_memory_usage'
            ),
            'classes': ('collapse',)
        }),
        ('Error Rates', {
            'fields': ('error_rate', 'timeout_rate', 'retry_rate'),
            'classes': ('collapse',)
        }),
        ('Quality Scores', {
            'fields': ('data_quality_score', 'reliability_score'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('calculated_at',),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'period_start'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'workflow'
        )

    def avg_execution_time_display(self, obj):
        """Display average execution time in readable format"""
        seconds = obj.avg_execution_time
        if seconds < 60:
            return f"{seconds:.2f}s"
        else:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{int(minutes)}m {seconds:.1f}s"

    avg_execution_time_display.short_description = 'Avg Execution Time'
    avg_execution_time_display.admin_order_field = 'avg_execution_time'

    def error_rate_display(self, obj):
        """Display error rate with color coding"""
        rate = obj.error_rate
        if rate < 1:
            color = 'green'
        elif rate < 5:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {};">{:.2f}%</span>',
            color, rate
        )

    error_rate_display.short_description = 'Error Rate'
    error_rate_display.admin_order_field = 'error_rate'


@admin.register(AnalyticsAlert)
class AnalyticsAlertAdmin(admin.ModelAdmin):
    """Analytics alert admin"""

    list_display = [
        'name', 'organization', 'alert_type', 'severity',
        'metric_name', 'is_active', 'trigger_count', 'last_triggered_at'
    ]

    list_filter = [
        'alert_type', 'severity', 'is_active', 'created_at', 'organization'
    ]

    search_fields = [
        'name', 'description', 'metric_name', 'organization__name'
    ]

    readonly_fields = [
        'last_triggered_at', 'trigger_count', 'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Alert Information', {
            'fields': (
                'name', 'description', 'organization', 'alert_type', 'severity'
            )
        }),
        ('Conditions', {
            'fields': ('metric_name', 'condition', 'threshold_config'),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': ('notification_channels', 'notification_config'),
            'classes': ('collapse',)
        }),
        ('Status & History', {
            'fields': (
                'is_active', 'last_triggered_at', 'trigger_count'
            )
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