"""
Analytics Serializers - API serialization for analytics and reporting
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsReport,
    AnalyticsMetric, UsageAnalytics, PerformanceMetrics, AnalyticsAlert
)
from apps.workflows.models import Workflow
from apps.organizations.models import Organization


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for nested serialization"""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = fields


class WorkflowBasicSerializer(serializers.ModelSerializer):
    """Basic workflow information for nested serialization"""

    class Meta:
        model = Workflow
        fields = ['id', 'name', 'description', 'status']
        read_only_fields = fields


class AnalyticsWidgetSerializer(serializers.ModelSerializer):
    """Analytics widget serializer"""

    class Meta:
        model = AnalyticsWidget
        fields = [
            'id', 'title', 'description', 'widget_type', 'chart_type',
            'query_config', 'display_config', 'size_config', 'data_source',
            'auto_refresh', 'refresh_interval', 'position_x', 'position_y',
            'width', 'height', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AnalyticsWidgetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating analytics widgets"""

    dashboard_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = AnalyticsWidget
        fields = [
            'dashboard_id', 'title', 'description', 'widget_type', 'chart_type',
            'query_config', 'display_config', 'size_config', 'data_source',
            'auto_refresh', 'refresh_interval', 'position_x', 'position_y',
            'width', 'height'
        ]

    def validate_dashboard_id(self, value):
        """Validate dashboard exists and user has access"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            dashboard = AnalyticsDashboard.objects.get(
                id=value,
                organization=organization
            )
            return dashboard
        except AnalyticsDashboard.DoesNotExist:
            raise serializers.ValidationError("Dashboard not found or access denied")

    def validate_query_config(self, value):
        """Validate query configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Query config must be a JSON object")
        return value

    def validate_display_config(self, value):
        """Validate display configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Display config must be a JSON object")
        return value

    def create(self, validated_data):
        """Create analytics widget"""
        dashboard = validated_data.pop('dashboard_id')

        widget = AnalyticsWidget.objects.create(
            dashboard=dashboard,
            **validated_data
        )

        return widget


class AnalyticsDashboardSerializer(serializers.ModelSerializer):
    """Analytics dashboard serializer"""

    created_by = UserBasicSerializer(read_only=True)
    shared_with_users = UserBasicSerializer(many=True, read_only=True)
    widgets = AnalyticsWidgetSerializer(many=True, read_only=True)
    widget_count = serializers.SerializerMethodField()

    class Meta:
        model = AnalyticsDashboard
        fields = [
            'id', 'name', 'description', 'dashboard_type', 'layout',
            'filters', 'refresh_interval', 'is_public', 'shared_with_users',
            'is_active', 'widgets', 'widget_count', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_by', 'created_at', 'updated_at', 'widget_count'
        ]

    def get_widget_count(self, obj):
        """Get number of widgets in dashboard"""
        return obj.widgets.filter(is_active=True).count()


class AnalyticsDashboardCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating analytics dashboards"""

    class Meta:
        model = AnalyticsDashboard
        fields = [
            'name', 'description', 'dashboard_type', 'layout',
            'filters', 'refresh_interval', 'is_public'
        ]

    def validate_layout(self, value):
        """Validate layout configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Layout must be a JSON object")
        return value

    def validate_filters(self, value):
        """Validate filters configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be a JSON object")
        return value


class AnalyticsReportSerializer(serializers.ModelSerializer):
    """Analytics report serializer"""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = AnalyticsReport
        fields = [
            'id', 'name', 'description', 'report_type', 'report_config',
            'filters', 'schedule_expression', 'timezone', 'delivery_method',
            'recipients', 'delivery_config', 'is_active', 'last_generated_at',
            'next_generation_at', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'last_generated_at', 'created_by', 'created_at', 'updated_at'
        ]


class AnalyticsReportCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating analytics reports"""

    class Meta:
        model = AnalyticsReport
        fields = [
            'name', 'description', 'report_type', 'report_config',
            'filters', 'schedule_expression', 'timezone', 'delivery_method',
            'recipients', 'delivery_config', 'next_generation_at'
        ]

    def validate_report_config(self, value):
        """Validate report configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Report config must be a JSON object")
        return value

    def validate_filters(self, value):
        """Validate filters configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be a JSON object")
        return value

    def validate_recipients(self, value):
        """Validate recipients list"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Recipients must be a list")

        # Validate email addresses if delivery method is email
        delivery_method = self.initial_data.get('delivery_method', '')
        if delivery_method == 'email':
            import re
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            for recipient in value:
                if not email_pattern.match(recipient):
                    raise serializers.ValidationError(f"Invalid email address: {recipient}")

        return value

    def validate_schedule_expression(self, value):
        """Validate cron expression"""
        # Basic validation - in production, use croniter library
        parts = value.split()
        if len(parts) != 5:
            raise serializers.ValidationError(
                "Schedule expression must be a valid cron expression with 5 parts"
            )
        return value


class AnalyticsMetricSerializer(serializers.ModelSerializer):
    """Analytics metric serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    formatted_value = serializers.SerializerMethodField()

    class Meta:
        model = AnalyticsMetric
        fields = [
            'id', 'name', 'metric_type', 'category', 'value', 'unit',
            'formatted_value', 'aggregation_period', 'period_start',
            'period_end', 'workflow', 'filters', 'metadata', 'calculated_at'
        ]
        read_only_fields = fields

    def get_formatted_value(self, obj):
        """Get formatted value with unit"""
        if obj.unit:
            if obj.unit == '%':
                return f"{obj.value:.1f}%"
            elif obj.unit == 'seconds':
                if obj.value < 60:
                    return f"{obj.value:.2f}s"
                else:
                    minutes = obj.value // 60
                    seconds = obj.value % 60
                    return f"{int(minutes)}m {seconds:.1f}s"
            else:
                return f"{obj.value} {obj.unit}"
        return str(obj.value)


class UsageAnalyticsSerializer(serializers.ModelSerializer):
    """Usage analytics serializer"""

    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = UsageAnalytics
        fields = [
            'id', 'date', 'active_users', 'new_users', 'total_users',
            'workflows_created', 'workflows_executed', 'total_workflows',
            'total_executions', 'successful_executions', 'failed_executions',
            'success_rate', 'average_execution_time', 'total_compute_hours',
            'total_storage_gb', 'api_calls_count', 'feature_usage', 'created_at'
        ]
        read_only_fields = fields


class PerformanceMetricsSerializer(serializers.ModelSerializer):
    """Performance metrics serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    avg_execution_time_formatted = serializers.SerializerMethodField()

    class Meta:
        model = PerformanceMetrics
        fields = [
            'id', 'workflow', 'period_start', 'period_end', 'avg_execution_time',
            'avg_execution_time_formatted', 'min_execution_time', 'max_execution_time',
            'p95_execution_time', 'executions_per_hour', 'peak_concurrent_executions',
            'avg_cpu_usage', 'avg_memory_usage', 'peak_memory_usage',
            'error_rate', 'timeout_rate', 'retry_rate', 'data_quality_score',
            'reliability_score', 'calculated_at'
        ]
        read_only_fields = fields

    def get_avg_execution_time_formatted(self, obj):
        """Get formatted average execution time"""
        seconds = obj.avg_execution_time
        if seconds < 60:
            return f"{seconds:.2f}s"
        else:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{int(minutes)}m {seconds:.1f}s"


class AnalyticsAlertSerializer(serializers.ModelSerializer):
    """Analytics alert serializer"""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = AnalyticsAlert
        fields = [
            'id', 'name', 'description', 'alert_type', 'severity',
            'metric_name', 'condition', 'threshold_config',
            'notification_channels', 'notification_config', 'is_active',
            'last_triggered_at', 'trigger_count', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'last_triggered_at', 'trigger_count', 'created_by',
            'created_at', 'updated_at'
        ]


class AnalyticsAlertCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating analytics alerts"""

    class Meta:
        model = AnalyticsAlert
        fields = [
            'name', 'description', 'alert_type', 'severity', 'metric_name',
            'condition', 'threshold_config', 'notification_channels',
            'notification_config'
        ]

    def validate_condition(self, value):
        """Validate alert condition"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Condition must be a JSON object")
        return value

    def validate_threshold_config(self, value):
        """Validate threshold configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Threshold config must be a JSON object")

        # Validate required fields
        if 'value' not in value:
            raise serializers.ValidationError("Threshold config must include 'value' field")

        if 'operator' not in value:
            value['operator'] = 'less_than'  # Default operator

        valid_operators = ['less_than', 'greater_than', 'equals', 'not_equals']
        if value['operator'] not in valid_operators:
            raise serializers.ValidationError(f"Invalid operator. Must be one of: {valid_operators}")

        return value

    def validate_notification_channels(self, value):
        """Validate notification channels"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Notification channels must be a list")

        valid_channels = ['email', 'slack', 'webhook', 'sms']
        for channel in value:
            if channel not in valid_channels:
                raise serializers.ValidationError(f"Invalid notification channel: {channel}")

        return value


class DashboardStatsSerializer(serializers.Serializer):
    """Dashboard statistics serializer"""

    period_days = serializers.IntegerField()
    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    total_workflows = serializers.IntegerField()
    active_workflows = serializers.IntegerField()
    active_members = serializers.IntegerField()
    execution_trend = serializers.FloatField()
    avg_execution_time = serializers.DurationField()


class WorkflowAnalyticsSerializer(serializers.Serializer):
    """Workflow-specific analytics serializer"""

    workflow = serializers.DictField()
    period_days = serializers.IntegerField()
    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_execution_time = serializers.DurationField()
    daily_trends = serializers.ListField(child=serializers.DictField())


class AnalyticsTrendsSerializer(serializers.Serializer):
    """Analytics trends serializer"""

    dates = serializers.ListField(child=serializers.CharField())
    active_users = serializers.ListField(child=serializers.IntegerField())
    executions = serializers.ListField(child=serializers.IntegerField())
    success_rates = serializers.ListField(child=serializers.FloatField())
    compute_hours = serializers.ListField(child=serializers.FloatField())


class AlertTestSerializer(serializers.Serializer):
    """Alert test result serializer"""

    alert_triggered = serializers.BooleanField()
    current_value = serializers.FloatField()
    threshold = serializers.DictField()
    message = serializers.CharField()


class ReportGenerationSerializer(serializers.Serializer):
    """Report generation result serializer"""

    message = serializers.CharField()
    data = serializers.DictField()


class WidgetDataSerializer(serializers.Serializer):
    """Widget data serializer"""

    value = serializers.FloatField(required=False)
    data = serializers.ListField(child=serializers.DictField(), required=False)
    error = serializers.CharField(required=False)