"""
Execution Serializers - API serialization for execution management
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    ExecutionQueue, ExecutionHistory, ExecutionAlert,
    ExecutionResource, ExecutionSchedule
)
from apps.workflows.models import Workflow


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


class ExecutionQueueSerializer(serializers.ModelSerializer):
    """Execution queue serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    triggered_by = UserBasicSerializer(read_only=True)
    can_retry = serializers.ReadOnlyField()
    duration = serializers.SerializerMethodField()

    class Meta:
        model = ExecutionQueue
        fields = [
            'id', 'execution_id', 'workflow', 'priority', 'status',
            'trigger_type', 'trigger_data', 'triggered_by', 'scheduled_at',
            'max_attempts', 'attempt_count', 'input_data', 'variables',
            'created_at', 'started_at', 'completed_at', 'duration',
            'error_message', 'error_details', 'can_retry'
        ]
        read_only_fields = [
            'id', 'execution_id', 'created_at', 'started_at', 'completed_at',
            'attempt_count', 'error_message', 'error_details', 'can_retry'
        ]

    def get_duration(self, obj):
        """Calculate execution duration"""
        if obj.started_at and obj.completed_at:
            delta = obj.completed_at - obj.started_at
            return delta.total_seconds()
        return None


class ExecutionQueueCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating execution queue entries"""

    workflow_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ExecutionQueue
        fields = [
            'workflow_id', 'priority', 'trigger_type', 'trigger_data',
            'input_data', 'variables', 'scheduled_at'
        ]

    def validate_workflow_id(self, value):
        """Validate workflow exists and user has access"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            workflow = Workflow.objects.get(
                id=value,
                organization=organization
            )
            return workflow
        except Workflow.DoesNotExist:
            raise serializers.ValidationError("Workflow not found or access denied")

    def create(self, validated_data):
        """Create execution queue entry"""
        import uuid

        workflow = validated_data.pop('workflow_id')
        request = self.context['request']

        execution = ExecutionQueue.objects.create(
            workflow=workflow,
            execution_id=f"api-{uuid.uuid4().hex[:8]}",
            triggered_by=request.user,
            **validated_data
        )

        return execution


class ExecutionHistorySerializer(serializers.ModelSerializer):
    """Execution history serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    triggered_by = UserBasicSerializer(read_only=True)
    duration_seconds = serializers.ReadOnlyField()
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = ExecutionHistory
        fields = [
            'id', 'execution_id', 'workflow', 'status', 'started_at',
            'completed_at', 'execution_time', 'duration_seconds',
            'nodes_executed', 'nodes_failed', 'memory_peak_mb',
            'trigger_type', 'triggered_by', 'input_size_bytes',
            'output_size_bytes', 'error_type', 'error_message',
            'success_rate', 'created_at'
        ]
        read_only_fields = fields


class ExecutionAlertSerializer(serializers.ModelSerializer):
    """Execution alert serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    acknowledged_by = UserBasicSerializer(read_only=True)
    notified_users = UserBasicSerializer(many=True, read_only=True)

    class Meta:
        model = ExecutionAlert
        fields = [
            'id', 'workflow', 'alert_type', 'status', 'title', 'message',
            'execution_id', 'severity', 'notified_users', 'notification_sent',
            'acknowledged_by', 'acknowledged_at', 'resolved_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'acknowledged_by', 'acknowledged_at', 'resolved_at',
            'created_at', 'updated_at'
        ]


class ExecutionAlertCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating execution alerts"""

    workflow_id = serializers.UUIDField(write_only=True)
    notify_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = ExecutionAlert
        fields = [
            'workflow_id', 'alert_type', 'title', 'message', 'execution_id',
            'severity', 'notify_user_ids'
        ]

    def validate_workflow_id(self, value):
        """Validate workflow exists and user has access"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            workflow = Workflow.objects.get(
                id=value,
                organization=organization
            )
            return workflow
        except Workflow.DoesNotExist:
            raise serializers.ValidationError("Workflow not found or access denied")

    def create(self, validated_data):
        """Create execution alert"""
        workflow = validated_data.pop('workflow_id')
        notify_user_ids = validated_data.pop('notify_user_ids', [])
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        alert = ExecutionAlert.objects.create(
            organization=organization,
            workflow=workflow,
            **validated_data
        )

        # Add notified users
        if notify_user_ids:
            users = User.objects.filter(
                id__in=notify_user_ids,
                organization_memberships__organization=organization
            )
            alert.notified_users.set(users)

        return alert


class ExecutionResourceSerializer(serializers.ModelSerializer):
    """Execution resource serializer"""

    average_cpu_usage = serializers.ReadOnlyField()
    average_memory_usage = serializers.ReadOnlyField()

    class Meta:
        model = ExecutionResource
        fields = [
            'id', 'execution_id', 'cpu_seconds', 'memory_mb_seconds',
            'storage_mb', 'network_bytes', 'start_time', 'end_time',
            'duration_seconds', 'node_resource_usage', 'average_cpu_usage',
            'average_memory_usage', 'created_at'
        ]
        read_only_fields = fields


class ExecutionScheduleSerializer(serializers.ModelSerializer):
    """Execution schedule serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    should_disable = serializers.ReadOnlyField()

    class Meta:
        model = ExecutionSchedule
        fields = [
            'id', 'workflow', 'cron_expression', 'timezone', 'status',
            'max_concurrent_executions', 'timeout_minutes', 'next_run_time',
            'last_run_time', 'run_count', 'failure_count', 'max_failures',
            'failure_notification_threshold', 'should_disable',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'next_run_time', 'last_run_time', 'run_count',
            'failure_count', 'should_disable', 'created_at', 'updated_at'
        ]


class ExecutionScheduleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating execution schedules"""

    workflow_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ExecutionSchedule
        fields = [
            'workflow_id', 'cron_expression', 'timezone', 'status',
            'max_concurrent_executions', 'timeout_minutes', 'max_failures',
            'failure_notification_threshold'
        ]

    def validate_workflow_id(self, value):
        """Validate workflow exists and user has access"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            workflow = Workflow.objects.get(
                id=value,
                organization=organization
            )

            # Check if schedule already exists
            if hasattr(workflow, 'schedule'):
                raise serializers.ValidationError("Workflow already has a schedule")

            return workflow
        except Workflow.DoesNotExist:
            raise serializers.ValidationError("Workflow not found or access denied")

    def validate_cron_expression(self, value):
        """Validate cron expression format"""
        # Basic validation - in production, use croniter library
        parts = value.split()
        if len(parts) != 5:
            raise serializers.ValidationError(
                "Cron expression must have 5 parts: minute hour day month weekday"
            )
        return value

    def create(self, validated_data):
        """Create execution schedule"""
        from django.utils import timezone

        workflow = validated_data.pop('workflow_id')

        # Calculate next run time (simplified - use croniter in production)
        next_run_time = timezone.now()

        schedule = ExecutionSchedule.objects.create(
            workflow=workflow,
            next_run_time=next_run_time,
            **validated_data
        )

        return schedule


class ExecutionStatsSerializer(serializers.Serializer):
    """Execution statistics serializer"""

    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_execution_time = serializers.DurationField()
    period_days = serializers.IntegerField()

    # Trends
    daily_trends = serializers.ListField(
        child=serializers.DictField()
    )

    # Top workflows
    top_workflows = serializers.ListField(
        child=serializers.DictField()
    )


class ExecutionPerformanceSerializer(serializers.Serializer):
    """Execution performance metrics serializer"""

    average_execution_time = serializers.DurationField()
    average_nodes_executed = serializers.FloatField()
    average_memory_usage = serializers.FloatField()

    performance_trends = serializers.ListField(
        child=serializers.DictField()
    )


class ExecutionTriggerSerializer(serializers.Serializer):
    """Serializer for triggering workflow executions"""

    input_data = serializers.JSONField(default=dict)
    variables = serializers.JSONField(default=dict)
    priority = serializers.ChoiceField(
        choices=ExecutionQueue.PRIORITY_CHOICES,
        default='normal'
    )

    def validate_input_data(self, value):
        """Validate input data structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Input data must be a JSON object")
        return value

    def validate_variables(self, value):
        """Validate variables structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Variables must be a JSON object")
        return value


class ExecutionStatusSerializer(serializers.Serializer):
    """Serializer for execution status responses"""

    execution_id = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField(required=False)
    started_at = serializers.DateTimeField(required=False)
    completed_at = serializers.DateTimeField(required=False)
    execution_time = serializers.DurationField(required=False)
    error_message = serializers.CharField(required=False)