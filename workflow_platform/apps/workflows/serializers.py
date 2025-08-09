"""
Workflow Serializers - Comprehensive API serialization
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Workflow, WorkflowExecution, WorkflowTemplate,
    WorkflowComment, WorkflowShare, WorkflowCategory
)
from apps.organizations.models import Organization
from apps.nodes.models import NodeType


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for nested serialization"""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = fields


class WorkflowCategorySerializer(serializers.ModelSerializer):
    """Workflow category serializer"""

    class Meta:
        model = WorkflowCategory
        fields = ['id', 'name', 'description', 'icon', 'color']


class WorkflowSerializer(serializers.ModelSerializer):
    """Standard workflow serializer"""

    created_by = UserBasicSerializer(read_only=True)
    updated_by = UserBasicSerializer(read_only=True)
    category = WorkflowCategorySerializer(read_only=True)
    success_rate = serializers.ReadOnlyField()
    node_count = serializers.SerializerMethodField()

    class Meta:
        model = Workflow
        fields = [
            'id', 'name', 'description', 'category', 'tags', 'status',
            'trigger_type', 'version', 'is_latest_version', 'is_public',
            'is_template', 'created_by', 'updated_by', 'created_at', 'updated_at',
            'total_executions', 'successful_executions', 'failed_executions',
            'last_executed_at', 'average_execution_time', 'success_rate', 'node_count'
        ]
        read_only_fields = [
            'id', 'created_by', 'updated_by', 'created_at', 'updated_at',
            'total_executions', 'successful_executions', 'failed_executions',
            'last_executed_at', 'average_execution_time', 'success_rate', 'node_count'
        ]

    def get_node_count(self, obj):
        """Get number of nodes in workflow"""
        return len(obj.nodes)


class WorkflowCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating workflows"""

    category_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Workflow
        fields = [
            'name', 'description', 'category_id', 'tags', 'nodes', 'connections',
            'variables', 'trigger_type', 'execution_timeout', 'max_retries',
            'retry_delay', 'parallel_execution', 'schedule_expression',
            'schedule_timezone', 'settings', 'error_handling'
        ]

    def validate_name(self, value):
        """Validate workflow name uniqueness within organization"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        if Workflow.objects.filter(
                organization=organization,
                name=value,
                is_latest_version=True
        ).exists():
            raise serializers.ValidationError("Workflow with this name already exists")

        return value

    def validate_nodes(self, value):
        """Validate workflow nodes"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Nodes must be a list")

        if len(value) == 0:
            raise serializers.ValidationError("Workflow must have at least one node")

        # Validate node structure
        for i, node in enumerate(value):
            if not isinstance(node, dict):
                raise serializers.ValidationError(f"Node {i} must be an object")

            required_fields = ['id', 'type']
            for field in required_fields:
                if field not in node:
                    raise serializers.ValidationError(f"Node {i} missing required field: {field}")

            # Validate node type exists
            try:
                NodeType.objects.get(name=node['type'], is_active=True)
            except NodeType.DoesNotExist:
                raise serializers.ValidationError(f"Node type '{node['type']}' not found")

        return value

    def validate_connections(self, value):
        """Validate workflow connections"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Connections must be a list")

        # Validate connection structure
        for i, connection in enumerate(value):
            if not isinstance(connection, dict):
                raise serializers.ValidationError(f"Connection {i} must be an object")

            required_fields = ['source', 'target']
            for field in required_fields:
                if field not in connection:
                    raise serializers.ValidationError(f"Connection {i} missing required field: {field}")

        return value

    def create(self, validated_data):
        """Create workflow with category lookup"""
        category_id = validated_data.pop('category_id', None)

        if category_id:
            try:
                category = WorkflowCategory.objects.get(id=category_id)
                validated_data['category'] = category
            except WorkflowCategory.DoesNotExist:
                raise serializers.ValidationError("Invalid category ID")

        return super().create(validated_data)


class WorkflowDetailSerializer(WorkflowSerializer):
    """Detailed workflow serializer with full information"""

    parent_workflow = WorkflowSerializer(read_only=True)
    versions = serializers.SerializerMethodField()
    recent_executions = serializers.SerializerMethodField()
    shared_with_users = serializers.SerializerMethodField()

    class Meta(WorkflowSerializer.Meta):
        fields = WorkflowSerializer.Meta.fields + [
            'nodes', 'connections', 'variables', 'execution_timeout',
            'max_retries', 'retry_delay', 'parallel_execution',
            'schedule_expression', 'schedule_timezone', 'settings',
            'error_handling', 'parent_workflow', 'versions',
            'recent_executions', 'shared_with_users'
        ]

    def get_versions(self, obj):
        """Get workflow versions"""
        parent = obj.parent_workflow or obj
        versions = Workflow.objects.filter(
            models.Q(id=parent.id) | models.Q(parent_workflow=parent)
        ).order_by('-version')[:5]  # Last 5 versions

        return [{
            'id': v.id,
            'version': v.version,
            'created_at': v.created_at,
            'created_by': v.created_by.username,
            'is_latest': v.is_latest_version
        } for v in versions]

    def get_recent_executions(self, obj):
        """Get recent executions"""
        executions = obj.executions.order_by('-started_at')[:5]
        return WorkflowExecutionSerializer(executions, many=True).data

    def get_shared_with_users(self, obj):
        """Get users workflow is shared with"""
        shares = obj.shares.select_related('shared_with')
        return [{
            'user': UserBasicSerializer(share.shared_with).data,
            'permission': share.permission,
            'shared_at': share.shared_at
        } for share in shares]


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    """Workflow execution serializer"""

    workflow = serializers.SerializerMethodField()
    triggered_by = UserBasicSerializer(read_only=True)
    duration = serializers.ReadOnlyField()

    class Meta:
        model = WorkflowExecution
        fields = [
            'id', 'workflow', 'status', 'trigger_source', 'triggered_by',
            'started_at', 'completed_at', 'execution_time', 'duration',
            'input_data', 'output_data', 'error_message', 'error_details',
            'nodes_executed', 'nodes_failed', 'memory_usage_mb',
            'cpu_usage_percent', 'retry_count'
        ]
        read_only_fields = fields

    def get_workflow(self, obj):
        """Get basic workflow info"""
        return {
            'id': obj.workflow.id,
            'name': obj.workflow.name,
            'version': obj.workflow.version
        }


class WorkflowExecutionDetailSerializer(WorkflowExecutionSerializer):
    """Detailed execution serializer with logs"""

    node_logs = serializers.SerializerMethodField()

    class Meta(WorkflowExecutionSerializer.Meta):
        fields = WorkflowExecutionSerializer.Meta.fields + ['node_logs']

    def get_node_logs(self, obj):
        """Get node execution logs"""
        from apps.nodes.serializers import NodeExecutionLogSerializer
        logs = obj.node_logs.order_by('started_at')
        return NodeExecutionLogSerializer(logs, many=True).data


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    """Workflow template serializer"""

    workflow = WorkflowSerializer(read_only=True)

    class Meta:
        model = WorkflowTemplate
        fields = [
            'id', 'workflow', 'title', 'short_description', 'long_description',
            'difficulty', 'industry', 'use_case', 'thumbnail', 'screenshots',
            'usage_count', 'rating', 'rating_count', 'is_featured', 'is_official',
            'published_at', 'required_integrations', 'required_plan'
        ]
        read_only_fields = fields


class WorkflowCommentSerializer(serializers.ModelSerializer):
    """Workflow comment serializer"""

    author = UserBasicSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowComment
        fields = [
            'id', 'author', 'content', 'node_id', 'parent_comment',
            'created_at', 'updated_at', 'replies'
        ]
        read_only_fields = ['id', 'author', 'created_at', 'updated_at', 'replies']

    def get_replies(self, obj):
        """Get comment replies"""
        if obj.parent_comment is None:  # Only get replies for top-level comments
            replies = obj.replies.order_by('created_at')
            return WorkflowCommentSerializer(replies, many=True, context=self.context).data
        return []


class WorkflowShareSerializer(serializers.ModelSerializer):
    """Workflow sharing serializer"""

    shared_with = UserBasicSerializer(read_only=True)
    shared_by = UserBasicSerializer(read_only=True)
    workflow = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowShare
        fields = [
            'id', 'workflow', 'shared_with', 'shared_by', 'permission', 'shared_at'
        ]
        read_only_fields = fields

    def get_workflow(self, obj):
        """Get basic workflow info"""
        return {
            'id': obj.workflow.id,
            'name': obj.workflow.name
        }


class WorkflowAnalyticsSerializer(serializers.Serializer):
    """Workflow analytics data serializer"""

    # Overview metrics
    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_execution_time = serializers.FloatField()

    # Time series data
    daily_stats = serializers.ListField(
        child=serializers.DictField()
    )

    # Node performance
    node_performance = serializers.ListField(
        child=serializers.DictField()
    )

    # Error analysis
    error_analysis = serializers.ListField(
        child=serializers.DictField()
    )

    # Performance trends
    performance_trends = serializers.DictField()


class WorkflowValidationSerializer(serializers.Serializer):
    """Workflow validation result serializer"""

    is_valid = serializers.BooleanField()
    errors = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    warnings = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    suggestions = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )


class WorkflowImportSerializer(serializers.Serializer):
    """Workflow import serializer"""

    name = serializers.CharField(max_length=255)
    workflow_data = serializers.JSONField()
    import_credentials = serializers.BooleanField(default=False)

    def validate_workflow_data(self, value):
        """Validate imported workflow data"""
        required_fields = ['nodes', 'connections']

        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(f"Missing required field: {field}")

        # Validate nodes
        if not isinstance(value['nodes'], list):
            raise serializers.ValidationError("Nodes must be a list")

        if len(value['nodes']) == 0:
            raise serializers.ValidationError("Workflow must have at least one node")

        # Validate connections
        if not isinstance(value['connections'], list):
            raise serializers.ValidationError("Connections must be a list")

        return value

    def create(self, validated_data):
        """Create workflow from imported data"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        workflow_data = validated_data['workflow_data']

        workflow = Workflow.objects.create(
            organization=organization,
            name=validated_data['name'],
            description=workflow_data.get('description', ''),
            nodes=workflow_data['nodes'],
            connections=workflow_data['connections'],
            variables=workflow_data.get('variables', {}),
            trigger_type=workflow_data.get('trigger_type', 'manual'),
            execution_timeout=workflow_data.get('execution_timeout', 300),
            max_retries=workflow_data.get('max_retries', 3),
            retry_delay=workflow_data.get('retry_delay', 60),
            parallel_execution=workflow_data.get('parallel_execution', True),
            settings=workflow_data.get('settings', {}),
            error_handling=workflow_data.get('error_handling', {}),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        return workflow


class WorkflowExportSerializer(serializers.ModelSerializer):
    """Workflow export serializer"""

    class Meta:
        model = Workflow
        fields = [
            'name', 'description', 'nodes', 'connections', 'variables',
            'trigger_type', 'execution_timeout', 'max_retries', 'retry_delay',
            'parallel_execution', 'settings', 'error_handling', 'version'
        ]

    def to_representation(self, instance):
        """Custom representation for export"""
        data = super().to_representation(instance)

        # Add export metadata
        data['export_metadata'] = {
            'exported_at': timezone.now().isoformat(),
            'exported_by': self.context['request'].user.username,
            'original_id': str(instance.id),
            'platform': 'workflow_platform',
            'version': '1.0'
        }

        # Remove sensitive data
        for node in data.get('nodes', []):
            if 'credentials' in node.get('configuration', {}):
                node['configuration']['credentials'] = '***REMOVED***'

        return data


class WorkflowScheduleSerializer(serializers.Serializer):
    """Workflow scheduling serializer"""

    schedule_expression = serializers.CharField(max_length=255)
    schedule_timezone = serializers.CharField(max_length=50, default='UTC')
    is_enabled = serializers.BooleanField(default=True)

    def validate_schedule_expression(self, value):
        """Validate cron expression"""
        try:
            from croniter import croniter
            croniter(value)
            return value
        except Exception:
            raise serializers.ValidationError("Invalid cron expression")

    def validate_schedule_timezone(self, value):
        """Validate timezone"""
        import pytz

        try:
            pytz.timezone(value)
            return value
        except pytz.exceptions.UnknownTimeZoneError:
            raise serializers.ValidationError("Invalid timezone")


class WorkflowStatisticsSerializer(serializers.Serializer):
    """Organization workflow statistics serializer"""

    totals = serializers.DictField()
    recent_performance = serializers.DictField()
    popular_workflows = serializers.ListField(
        child=serializers.DictField()
    )


class WorkflowStatsSerializer(serializers.Serializer):
    """Workflow statistics serializer"""

    total_workflows = serializers.IntegerField()
    active_workflows = serializers.IntegerField()
    draft_workflows = serializers.IntegerField()
    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_execution_time = serializers.FloatField(allow_null=True)
    most_used_workflows = serializers.ListField(child=serializers.DictField())
    recent_workflows = serializers.ListField(child=serializers.DictField())


class WorkflowCloneSerializer(serializers.Serializer):
    """Workflow clone serializer"""

    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    modifications = serializers.DictField(required=False, default=dict)

    def validate_name(self, value):
        """Validate workflow name"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Workflow name cannot be empty")
        return value.strip()