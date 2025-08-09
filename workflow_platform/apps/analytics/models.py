"""
Analytics models for comprehensive monitoring and business intelligence
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.organizations.models import Organization
from apps.workflows.models import Workflow, WorkflowExecution
from apps.nodes.models import NodeType
import uuid
from datetime import timedelta


class AnalyticsDashboard(models.Model):
    """
    Custom analytics dashboards
    """

    DASHBOARD_TYPES = [
        ('overview', 'Overview'),
        ('performance', 'Performance'),
        ('usage', 'Usage'),
        ('errors', 'Errors'),
        ('business', 'Business'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='dashboards')

    # Dashboard configuration
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dashboard_type = models.CharField(max_length=20, choices=DASHBOARD_TYPES, default='custom')

    # Layout and widgets
    layout = models.JSONField(default=dict)  # Grid layout configuration
    widgets = models.JSONField(default=list)  # Widget configurations

    # Sharing and permissions
    is_public = models.BooleanField(default=False)
    shared_with_users = models.ManyToManyField(User, blank=True, related_name='shared_dashboards')

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_dashboards')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_dashboards'
        indexes = [
            models.Index(fields=['organization', 'dashboard_type']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class MetricDefinition(models.Model):
    """
    Custom metric definitions for analytics
    """

    METRIC_TYPES = [
        ('count', 'Count'),
        ('sum', 'Sum'),
        ('average', 'Average'),
        ('percentage', 'Percentage'),
        ('ratio', 'Ratio'),
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
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='metric_definitions')

    # Metric configuration
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES)

    # Data source
    source_model = models.CharField(max_length=100)  # e.g., 'WorkflowExecution'
    source_field = models.CharField(max_length=100, blank=True)  # Field to aggregate
    filters = models.JSONField(default=dict)  # Query filters

    # Aggregation
    aggregation_period = models.CharField(max_length=20, choices=AGGREGATION_PERIODS, default='day')

    # Display
    unit = models.CharField(max_length=50, blank=True)  # e.g., 'ms', '%', '$'
    format_string = models.CharField(max_length=100, blank=True)  # e.g., '{value:.2f}%'

    # Status
    is_active = models.BooleanField(default=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_metrics')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'metric_definitions'
        unique_together = ['organization', 'name']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['metric_type', 'aggregation_period']),
        ]

    def __str__(self):
        return f"{self.name} ({self.metric_type})"


class MetricValue(models.Model):
    """
    Stored metric values for time series data
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric_definition = models.ForeignKey(MetricDefinition, on_delete=models.CASCADE, related_name='values')

    # Time series data
    timestamp = models.DateTimeField()
    value = models.FloatField()

    # Additional dimensions
    dimensions = models.JSONField(default=dict, blank=True)  # e.g., {'workflow_id': 'xxx', 'node_type': 'http'}

    # Metadata
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'metric_values'
        unique_together = ['metric_definition', 'timestamp', 'dimensions']
        indexes = [
            models.Index(fields=['metric_definition', 'timestamp']),
            models.Index(fields=['timestamp', 'value']),
        ]

    def __str__(self):
        return f"{self.metric_definition.name}: {self.value} at {self.timestamp}"


class PerformanceSnapshot(models.Model):
    """
    System performance snapshots
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='performance_snapshots')

    # System metrics
    cpu_usage_percent = models.FloatField(default=0)
    memory_usage_mb = models.FloatField(default=0)
    disk_usage_percent = models.FloatField(default=0)

    # Application metrics
    active_workflows = models.IntegerField(default=0)
    running_executions = models.IntegerField(default=0)
    queued_executions = models.IntegerField(default=0)

    # Performance metrics
    avg_execution_time_ms = models.FloatField(default=0)
    api_response_time_ms = models.FloatField(default=0)
    database_query_time_ms = models.FloatField(default=0)

    # Error rates
    error_rate_percent = models.FloatField(default=0)
    timeout_rate_percent = models.FloatField(default=0)

    # Resource usage
    database_connections = models.IntegerField(default=0)
    redis_memory_mb = models.FloatField(default=0)

    # Timestamp
    snapshot_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'performance_snapshots'
        indexes = [
            models.Index(fields=['organization', 'snapshot_time']),
            models.Index(fields=['snapshot_time']),
        ]

    def __str__(self):
        return f"Performance snapshot for {self.organization.name} at {self.snapshot_time}"


class UsageStatistics(models.Model):
    """
    Daily usage statistics per organization
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='usage_statistics')

    # Date
    date = models.DateField()

    # Workflow metrics
    workflows_created = models.IntegerField(default=0)
    workflows_executed = models.IntegerField(default=0)
    workflows_active = models.IntegerField(default=0)

    # Execution metrics
    total_executions = models.IntegerField(default=0)
    successful_executions = models.IntegerField(default=0)
    failed_executions = models.IntegerField(default=0)
    avg_execution_time_ms = models.FloatField(default=0)

    # API usage
    api_calls = models.IntegerField(default=0)
    webhook_deliveries = models.IntegerField(default=0)

    # Resource usage
    compute_time_seconds = models.FloatField(default=0)
    storage_used_mb = models.FloatField(default=0)
    bandwidth_used_mb = models.FloatField(default=0)

    # User activity
    active_users = models.IntegerField(default=0)
    login_count = models.IntegerField(default=0)

    # Node usage
    node_executions = models.JSONField(default=dict)  # {'http_request': 150, 'email': 25}

    # Cost tracking
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        db_table = 'usage_statistics'
        unique_together = ['organization', 'date']
        indexes = [
            models.Index(fields=['organization', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Usage for {self.organization.name} on {self.date}"


class ErrorAnalytics(models.Model):
    """
    Error analytics and tracking
    """

    ERROR_TYPES = [
        ('workflow_error', 'Workflow Error'),
        ('node_error', 'Node Error'),
        ('system_error', 'System Error'),
        ('authentication_error', 'Authentication Error'),
        ('validation_error', 'Validation Error'),
        ('timeout_error', 'Timeout Error'),
        ('network_error', 'Network Error'),
        ('database_error', 'Database Error'),
    ]

    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='error_analytics')

    # Error details
    error_type = models.CharField(max_length=50, choices=ERROR_TYPES)
    error_message = models.TextField()
    error_code = models.CharField(max_length=100, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='medium')

    # Context
    workflow = models.ForeignKey(Workflow, on_delete=models.SET_NULL, null=True, blank=True)
    node_type = models.ForeignKey(NodeType, on_delete=models.SET_NULL, null=True, blank=True)
    execution_id = models.UUIDField(null=True, blank=True)

    # Stack trace and debugging info
    stack_trace = models.TextField(blank=True)
    context_data = models.JSONField(default=dict, blank=True)

    # Occurrence tracking
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    occurrence_count = models.IntegerField(default=1)

    # Resolution
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'error_analytics'
        indexes = [
            models.Index(fields=['organization', 'error_type']),
            models.Index(fields=['severity', 'is_resolved']),
            models.Index(fields=['first_seen', 'last_seen']),
        ]

    def __str__(self):
        return f"{self.error_type}: {self.error_message[:50]}"


class AlertRule(models.Model):
    """
    Alert rules for monitoring and notifications
    """

    CONDITION_TYPES = [
        ('threshold', 'Threshold'),
        ('percentage', 'Percentage'),
        ('rate', 'Rate'),
        ('anomaly', 'Anomaly'),
    ]

    OPERATORS = [
        ('>', 'Greater than'),
        ('<', 'Less than'),
        ('>=', 'Greater than or equal'),
        ('<=', 'Less than or equal'),
        ('=', 'Equal'),
        ('!=', 'Not equal'),
    ]

    NOTIFICATION_CHANNELS = [
        ('email', 'Email'),
        ('slack', 'Slack'),
        ('webhook', 'Webhook'),
        ('sms', 'SMS'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='alert_rules')

    # Rule configuration
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Condition
    metric = models.ForeignKey(MetricDefinition, on_delete=models.CASCADE, related_name='alert_rules')
    condition_type = models.CharField(max_length=20, choices=CONDITION_TYPES)
    operator = models.CharField(max_length=5, choices=OPERATORS)
    threshold_value = models.FloatField()

    # Time window
    evaluation_window_minutes = models.IntegerField(default=5)
    evaluation_frequency_minutes = models.IntegerField(default=1)

    # Notification
    notification_channels = models.JSONField(default=list)  # [{'type': 'email', 'config': {...}}]
    cooldown_minutes = models.IntegerField(default=30)  # Prevent spam

    # Filters
    filters = models.JSONField(default=dict, blank=True)  # Additional filtering

    # Status
    last_triggered = models.DateTimeField(null=True, blank=True)
    trigger_count = models.IntegerField(default=0)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_alert_rules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'alert_rules'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['metric', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class AlertInstance(models.Model):
    """
    Individual alert instances when rules are triggered
    """

    STATUS_CHOICES = [
        ('firing', 'Firing'),
        ('resolved', 'Resolved'),
        ('suppressed', 'Suppressed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='instances')

    # Alert details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='firing')
    triggered_value = models.FloatField()
    threshold_value = models.FloatField()

    # Context
    context_data = models.JSONField(default=dict, blank=True)

    # Timing
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Notifications
    notifications_sent = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'alert_instances'
        indexes = [
            models.Index(fields=['alert_rule', 'status']),
            models.Index(fields=['triggered_at']),
        ]

    def __str__(self):
        return f"Alert: {self.alert_rule.name} at {self.triggered_at}"


class BusinessMetrics(models.Model):
    """
    Business-level metrics and KPIs
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='business_metrics')

    # Date
    date = models.DateField()

    # Revenue impact metrics (if cost tracking is enabled)
    estimated_cost_savings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    automation_hours_saved = models.FloatField(default=0)

    # Efficiency metrics
    workflows_automated = models.IntegerField(default=0)
    manual_processes_replaced = models.IntegerField(default=0)
    error_reduction_percent = models.FloatField(default=0)

    # User adoption metrics
    active_users = models.IntegerField(default=0)
    new_workflows_created = models.IntegerField(default=0)
    workflow_adoption_rate = models.FloatField(default=0)

    # ROI metrics
    total_executions = models.IntegerField(default=0)
    avg_execution_value = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    # Custom KPIs
    custom_metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'business_metrics'
        unique_together = ['organization', 'date']
        indexes = [
            models.Index(fields=['organization', 'date']),
        ]

    def __str__(self):
        return f"Business metrics for {self.organization.name} on {self.date}"


class ReportTemplate(models.Model):
    """
    Report templates for scheduled reporting
    """

    REPORT_TYPES = [
        ('executive', 'Executive Summary'),
        ('operational', 'Operational Report'),
        ('performance', 'Performance Report'),
        ('usage', 'Usage Report'),
        ('custom', 'Custom Report'),
    ]

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('on_demand', 'On Demand'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='report_templates')

    # Template configuration
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)

    # Content configuration
    sections = models.JSONField(default=list)  # Report sections and widgets
    metrics = models.ManyToManyField(MetricDefinition, blank=True, related_name='report_templates')

    # Scheduling
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='on_demand')
    schedule_time = models.TimeField(null=True, blank=True)
    schedule_day = models.IntegerField(null=True, blank=True)  # Day of week/month

    # Distribution
    recipients = models.JSONField(default=list)  # Email addresses
    delivery_format = models.CharField(max_length=20, choices=[
        ('pdf', 'PDF'),
        ('email', 'Email'),
        ('dashboard', 'Dashboard Link'),
    ], default='pdf')

    # Status
    is_active = models.BooleanField(default=True)
    last_generated = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_report_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'report_templates'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['frequency', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.frequency})"


class GeneratedReport(models.Model):
    """
    Generated report instances
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, related_name='generated_reports')

    # Report details
    title = models.CharField(max_length=255)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Content
    report_data = models.JSONField(default=dict)  # Generated report data
    file_path = models.CharField(max_length=500, blank=True)  # PDF file path

    # Status
    generation_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')

    error_message = models.TextField(blank=True)

    # Metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'generated_reports'
        indexes = [
            models.Index(fields=['template', 'generated_at']),
            models.Index(fields=['generation_status']),
        ]

    def __str__(self):
        return f"{self.title} - {self.generated_at}"