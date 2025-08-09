"""
Execution Models - Workflow execution tracking and management
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.organizations.models import Organization
from apps.workflows.models import Workflow
import uuid
import json


class ExecutionQueue(models.Model):
    """Queue for managing workflow executions"""

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='execution_queue')

    # Execution metadata
    execution_id = models.CharField(max_length=255, unique=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Trigger information
    trigger_type = models.CharField(max_length=50)
    trigger_data = models.JSONField(default=dict)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # Scheduling
    scheduled_at = models.DateTimeField(default=timezone.now)
    max_attempts = models.IntegerField(default=3)
    attempt_count = models.IntegerField(default=0)

    # Execution context
    input_data = models.JSONField(default=dict)
    variables = models.JSONField(default=dict)

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Error handling
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict)

    class Meta:
        db_table = 'execution_queue'
        indexes = [
            models.Index(fields=['status', 'priority', 'scheduled_at']),
            models.Index(fields=['workflow', 'status']),
            models.Index(fields=['execution_id']),
        ]

    def __str__(self):
        return f"{self.workflow.name} - {self.execution_id} ({self.status})"

    def can_retry(self):
        """Check if execution can be retried"""
        return self.status == 'failed' and self.attempt_count < self.max_attempts

    def mark_started(self):
        """Mark execution as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.attempt_count += 1
        self.save()

    def mark_completed(self):
        """Mark execution as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def mark_failed(self, error_message, error_details=None):
        """Mark execution as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.save()


class ExecutionHistory(models.Model):
    """Historical execution data for analytics"""

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('timeout', 'Timeout'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='execution_history')
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='execution_history')

    # Execution metadata
    execution_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Timing data
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    execution_time = models.DurationField()

    # Performance metrics
    nodes_executed = models.IntegerField()
    nodes_failed = models.IntegerField(default=0)
    memory_peak_mb = models.FloatField(null=True, blank=True)

    # Trigger information
    trigger_type = models.CharField(max_length=50)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # Context data (compressed/summarized)
    input_size_bytes = models.IntegerField(default=0)
    output_size_bytes = models.IntegerField(default=0)

    # Error information
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'execution_history'
        indexes = [
            models.Index(fields=['organization', 'started_at']),
            models.Index(fields=['workflow', 'status']),
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['trigger_type', 'started_at']),
        ]

    def __str__(self):
        return f"{self.workflow.name} - {self.execution_id} ({self.status})"

    @property
    def duration_seconds(self):
        """Get execution duration in seconds"""
        return self.execution_time.total_seconds()

    @property
    def success_rate(self):
        """Get success rate for this workflow"""
        total = ExecutionHistory.objects.filter(workflow=self.workflow).count()
        successful = ExecutionHistory.objects.filter(workflow=self.workflow, status='success').count()
        if total > 0:
            return (successful / total) * 100
        return 0


class ExecutionAlert(models.Model):
    """Alerts for execution failures and issues"""

    ALERT_TYPES = [
        ('failure', 'Execution Failure'),
        ('timeout', 'Execution Timeout'),
        ('high_failure_rate', 'High Failure Rate'),
        ('resource_limit', 'Resource Limit Exceeded'),
        ('dependency_failure', 'Dependency Failure'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='execution_alerts')
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='execution_alerts')

    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Related execution (if applicable)
    execution_id = models.CharField(max_length=255, blank=True)

    # Alert metadata
    severity = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium')

    # Recipients and notifications
    notified_users = models.ManyToManyField(User, blank=True, related_name='execution_alerts')
    notification_sent = models.BooleanField(default=False)

    # Resolution
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acknowledged_alerts'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'execution_alerts'
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['workflow', 'alert_type']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.alert_type} - {self.workflow.name}"

    def acknowledge(self, user):
        """Acknowledge the alert"""
        self.status = 'acknowledged'
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()

    def resolve(self):
        """Mark alert as resolved"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.save()


class ExecutionResource(models.Model):
    """Resource usage tracking for executions"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_id = models.CharField(max_length=255, db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    # Resource usage
    cpu_seconds = models.FloatField(default=0)
    memory_mb_seconds = models.FloatField(default=0)  # Memory * time
    storage_mb = models.FloatField(default=0)
    network_bytes = models.FloatField(default=0)

    # Timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_seconds = models.FloatField()

    # Node-level breakdown
    node_resource_usage = models.JSONField(default=dict)  # Per-node resource usage

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'execution_resources'
        indexes = [
            models.Index(fields=['organization', 'start_time']),
            models.Index(fields=['execution_id']),
        ]

    def __str__(self):
        return f"Resources for {self.execution_id}"

    @property
    def average_cpu_usage(self):
        """Calculate average CPU usage during execution"""
        if self.duration_seconds > 0:
            return self.cpu_seconds / self.duration_seconds
        return 0

    @property
    def average_memory_usage(self):
        """Calculate average memory usage during execution"""
        if self.duration_seconds > 0:
            return self.memory_mb_seconds / self.duration_seconds
        return 0


class ExecutionSchedule(models.Model):
    """Scheduled execution management"""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('disabled', 'Disabled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.OneToOneField(Workflow, on_delete=models.CASCADE, related_name='schedule')

    # Schedule configuration
    cron_expression = models.CharField(max_length=100)
    timezone = models.CharField(max_length=50, default='UTC')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Execution settings
    max_concurrent_executions = models.IntegerField(default=1)
    timeout_minutes = models.IntegerField(default=60)

    # Tracking
    next_run_time = models.DateTimeField()
    last_run_time = models.DateTimeField(null=True, blank=True)
    run_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)

    # Error handling
    max_failures = models.IntegerField(default=5)
    failure_notification_threshold = models.IntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'execution_schedules'
        indexes = [
            models.Index(fields=['status', 'next_run_time']),
            models.Index(fields=['workflow']),
        ]

    def __str__(self):
        return f"Schedule for {self.workflow.name}"

    def update_next_run(self):
        """Calculate and update next run time"""
        # Implementation would use croniter or similar library
        # to calculate next run time based on cron expression
        pass

    def should_disable(self):
        """Check if schedule should be disabled due to failures"""
        return self.failure_count >= self.max_failures

    def record_execution(self, success=True):
        """Record execution result"""
        self.last_run_time = timezone.now()
        self.run_count += 1

        if success:
            self.failure_count = 0  # Reset failure count on success
        else:
            self.failure_count += 1

        self.update_next_run()
        self.save()