"""
Analytics Models - Data analytics and reporting
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Avg, Sum
from apps.organizations.models import Organization
from apps.workflows.models import Workflow
import uuid
import json


class AnalyticsDashboard(models.Model):
    """Custom analytics dashboards"""

    DASHBOARD_TYPES = [
        ('overview', 'Overview'),
        ('performance', 'Performance'),
        ('usage', 'Usage'),
        ('errors', 'Errors'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='dashboards')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_dashboards')

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dashboard_type = models.CharField(max_length=20, choices=DASHBOARD_TYPES, default='overview')

    # Dashboard configuration
    layout = models.JSONField(default=dict)  # Dashboard layout and widgets
    filters = models.JSONField(default=dict)  # Default filters
    refresh_interval = models.IntegerField(default=300)  # seconds

    # Sharing and permissions
    is_public = models.BooleanField(default=False)
    shared_with_users = models.ManyToManyField(User, blank=True, related_name='shared_dashboards')

    # Status
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_dashboards'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['dashboard_type']),
        ]

    def __str__(self):
        return f"{self.name} - {self.organization.name}"


class AnalyticsWidget(models.Model):
    """Individual widgets for dashboards"""

    WIDGET_TYPES = [
        ('metric', 'Metric Card'),
        ('chart', 'Chart'),
        ('table', 'Data Table'),
        ('gauge', 'Gauge'),
        ('timeline', 'Timeline'),
        ('heatmap', 'Heatmap'),
        ('custom', 'Custom'),
    ]

    CHART_TYPES = [
        ('line', 'Line Chart'),
        ('bar', 'Bar Chart'),
        ('pie', 'Pie Chart'),
        ('area', 'Area Chart'),
        ('scatter', 'Scatter Plot'),
        ('histogram', 'Histogram'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard = models.ForeignKey(AnalyticsDashboard, on_delete=models.CASCADE, related_name='widgets')

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES, default='metric')
    chart_type = models.CharField(max_length=20, choices=CHART_TYPES, blank=True)

    # Widget configuration
    query_config = models.JSONField(default=dict)  # Data query configuration
    display_config = models.JSONField(default=dict)  # Display settings
    size_config = models.JSONField(default=dict)  # Widget size and position

    # Data source
    data_source = models.CharField(max_length=100, default='executions')  # executions, workflows, etc.

    # Refresh settings
    auto_refresh = models.BooleanField(default=True)
    refresh_interval = models.IntegerField(default=60)  # seconds

    # Position in dashboard
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    width = models.IntegerField(default=4)
    height = models.IntegerField(default=3)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_widgets'
        indexes = [
            models.Index(fields=['dashboard', 'is_active']),
            models.Index(fields=['widget_type']),
        ]

    def __str__(self):
        return f"{self.title} ({self.widget_type})"


class AnalyticsReport(models.Model):
    """Scheduled analytics reports"""

    REPORT_TYPES = [
        ('daily', 'Daily Summary'),
        ('weekly', 'Weekly Report'),
        ('monthly', 'Monthly Report'),
        ('quarterly', 'Quarterly Report'),
        ('custom', 'Custom Report'),
    ]

    DELIVERY_METHODS = [
        ('email', 'Email'),
        ('slack', 'Slack'),
        ('webhook', 'Webhook'),
        ('download', 'Download Only'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='analytics_reports')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_reports')

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, default='weekly')

    # Report configuration
    report_config = models.JSONField(default=dict)  # Report structure and metrics
    filters = models.JSONField(default=dict)  # Data filters

    # Scheduling
    schedule_expression = models.CharField(max_length=100)  # Cron expression
    timezone = models.CharField(max_length=50, default='UTC')

    # Delivery
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS, default='email')
    recipients = models.JSONField(default=list)  # Email addresses, Slack channels, etc.
    delivery_config = models.JSONField(default=dict)  # Delivery-specific configuration

    # Status
    is_active = models.BooleanField(default=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)
    next_generation_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_reports'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['next_generation_at']),
        ]

    def __str__(self):
        return f"{self.name} - {self.report_type}"


class AnalyticsMetric(models.Model):
    """Calculated analytics metrics"""

    METRIC_TYPES = [
        ('count', 'Count'),
        ('sum', 'Sum'),
        ('average', 'Average'),
        ('percentage', 'Percentage'),
        ('ratio', 'Ratio'),
        ('rate', 'Rate'),
        ('duration', 'Duration'),
    ]

    AGGREGATION_PERIODS = [
        ('hour', 'Hourly'),
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
        ('quarter', 'Quarterly'),
        ('year', 'Yearly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='analytics_metrics')

    # Metric identification
    name = models.CharField(max_length=255)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES)
    category = models.CharField(max_length=100)  # workflows, executions, users, etc.

    # Value and metadata
    value = models.FloatField()
    unit = models.CharField(max_length=50, blank=True)  # %, seconds, count, etc.

    # Aggregation
    aggregation_period = models.CharField(max_length=20, choices=AGGREGATION_PERIODS)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Context
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, null=True, blank=True)
    filters = models.JSONField(default=dict)  # Additional filters used
    metadata = models.JSONField(default=dict)  # Additional metric metadata

    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics_metrics'
        unique_together = [
            'organization', 'name', 'category', 'aggregation_period', 'period_start'
        ]
        indexes = [
            models.Index(fields=['organization', 'category', 'period_start']),
            models.Index(fields=['name', 'period_start']),
            models.Index(fields=['workflow', 'metric_type']),
        ]

    def __str__(self):
        return f"{self.name}: {self.value} {self.unit}"


class UsageAnalytics(models.Model):
    """Usage analytics and trends"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='usage_analytics')

    # Date tracking
    date = models.DateField()

    # User metrics
    active_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    total_users = models.IntegerField(default=0)

    # Workflow metrics
    workflows_created = models.IntegerField(default=0)
    workflows_executed = models.IntegerField(default=0)
    total_workflows = models.IntegerField(default=0)

    # Execution metrics
    total_executions = models.IntegerField(default=0)
    successful_executions = models.IntegerField(default=0)
    failed_executions = models.IntegerField(default=0)
    average_execution_time = models.FloatField(default=0)  # seconds

    # Resource usage
    total_compute_hours = models.FloatField(default=0)
    total_storage_gb = models.FloatField(default=0)
    api_calls_count = models.IntegerField(default=0)

    # Feature usage
    feature_usage = models.JSONField(default=dict)  # Track feature adoption

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usage_analytics'
        unique_together = ['organization', 'date']
        indexes = [
            models.Index(fields=['organization', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Usage for {self.organization.name} on {self.date}"

    @property
    def success_rate(self):
        """Calculate execution success rate"""
        if self.total_executions > 0:
            return (self.successful_executions / self.total_executions) * 100
        return 0


class PerformanceMetrics(models.Model):
    """Performance metrics and benchmarks"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='performance_metrics')
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, null=True, blank=True)

    # Time period
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Execution performance
    avg_execution_time = models.FloatField(default=0)  # seconds
    min_execution_time = models.FloatField(default=0)
    max_execution_time = models.FloatField(default=0)
    p95_execution_time = models.FloatField(default=0)  # 95th percentile

    # Throughput metrics
    executions_per_hour = models.FloatField(default=0)
    peak_concurrent_executions = models.IntegerField(default=0)

    # Resource utilization
    avg_cpu_usage = models.FloatField(default=0)  # percentage
    avg_memory_usage = models.FloatField(default=0)  # MB
    peak_memory_usage = models.FloatField(default=0)  # MB

    # Error rates
    error_rate = models.FloatField(default=0)  # percentage
    timeout_rate = models.FloatField(default=0)  # percentage
    retry_rate = models.FloatField(default=0)  # percentage

    # Quality metrics
    data_quality_score = models.FloatField(default=0)  # 0-100
    reliability_score = models.FloatField(default=0)  # 0-100

    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'performance_metrics'
        indexes = [
            models.Index(fields=['organization', 'period_start']),
            models.Index(fields=['workflow', 'period_start']),
            models.Index(fields=['period_start']),
        ]

    def __str__(self):
        workflow_name = self.workflow.name if self.workflow else "All Workflows"
        return f"Performance for {workflow_name} ({self.period_start.date()})"


class AnalyticsAlert(models.Model):
    """Analytics-based alerts and notifications"""

    ALERT_TYPES = [
        ('threshold', 'Threshold Alert'),
        ('anomaly', 'Anomaly Detection'),
        ('trend', 'Trend Alert'),
        ('sla', 'SLA Violation'),
    ]

    SEVERITY_LEVELS = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='analytics_alerts')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    name = models.CharField(max_length=255)
    description = models.TextField()
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='warning')

    # Alert conditions
    metric_name = models.CharField(max_length=255)
    condition = models.JSONField(default=dict)  # Alert condition configuration
    threshold_config = models.JSONField(default=dict)  # Threshold settings

    # Notification settings
    notification_channels = models.JSONField(default=list)  # email, slack, etc.
    notification_config = models.JSONField(default=dict)

    # Status
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    trigger_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_alerts'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['metric_name', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.severity}"

    def trigger_alert(self, value, context=None):
        """Trigger the alert"""
        self.last_triggered_at = timezone.now()
        self.trigger_count += 1
        self.save()

        # Here would be logic to send notifications
        # based on notification_channels and notification_config