"""
Node Serializers
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    NodeType, NodeCategory, NodeCredential, NodeExecutionLog,
    NodeTypeRating, CustomNodeType, NodeTypeInstallation
)


class NodeCategorySerializer(serializers.ModelSerializer):
    """
    Node category serializer
    """

    node_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = NodeCategory
        fields = [
            'id', 'name', 'display_name', 'description', 'icon',
            'color', 'sort_order', 'node_count'
        ]


class NodeTypeSerializer(serializers.ModelSerializer):
    """
    Node type serializer with marketplace features
    """

    category = NodeCategorySerializer(read_only=True)
    author_name = serializers.SerializerMethodField()
    is_installed = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = NodeType
        fields = [
            'id', 'name', 'display_name', 'description', 'category',
            'node_type', 'source', 'icon', 'color', 'executor_class',
            'schema_version', 'properties_schema', 'inputs_schema',
            'outputs_schema', 'default_timeout', 'max_timeout',
            'supports_retry', 'supports_async', 'required_credentials',
            'required_packages', 'minimum_plan', 'documentation_url',
            'examples', 'is_active', 'is_beta', 'version', 'author_name',
            'repository_url', 'license', 'usage_count', 'rating',
            'rating_count', 'created_at', 'updated_at', 'is_installed',
            'average_rating'
        ]
        read_only_fields = [
            'id', 'usage_count', 'rating', 'rating_count', 'created_at',
            'updated_at', 'is_installed', 'average_rating'
        ]

    def get_author_name(self, obj):
        """Get author name"""
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return 'System'

    def get_is_installed(self, obj):
        """Check if node is installed in current organization"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                organization = request.user.organization_memberships.first().organization
                return NodeTypeInstallation.objects.filter(
                    organization=organization,
                    node_type=obj,
                    is_enabled=True
                ).exists()
            except Exception:
                pass
        return False

    def get_average_rating(self, obj):
        """Get formatted average rating"""
        return round(obj.rating, 1) if obj.rating else 0


class NodeTypeDetailSerializer(NodeTypeSerializer):
    """
    Detailed node type serializer with additional information
    """

    recent_ratings = serializers.SerializerMethodField()
    installation_count = serializers.SerializerMethodField()

    class Meta(NodeTypeSerializer.Meta):
        fields = NodeTypeSerializer.Meta.fields + [
            'recent_ratings', 'installation_count'
        ]

    def get_recent_ratings(self, obj):
        """Get recent ratings"""
        recent_ratings = obj.ratings.select_related('user').order_by('-created_at')[:5]
        return NodeTypeRatingSerializer(recent_ratings, many=True).data

    def get_installation_count(self, obj):
        """Get installation count"""
        return obj.installations.filter(is_enabled=True).count()


class NodeCredentialSerializer(serializers.ModelSerializer):
    """
    Node credential serializer with encryption handling
    """

    credential_data = serializers.JSONField(write_only=True)
    is_expired = serializers.ReadOnlyField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = NodeCredential
        fields = [
            'id', 'name', 'credential_type', 'service_name', 'description',
            'is_active', 'expires_at', 'last_used_at', 'created_by_name',
            'created_at', 'updated_at', 'credential_data', 'is_expired'
        ]
        read_only_fields = [
            'id', 'last_used_at', 'created_at', 'updated_at',
            'is_expired', 'created_by_name'
        ]
        extra_kwargs = {
            'encrypted_data': {'write_only': True},
            'encryption_key_id': {'write_only': True},
        }

    def get_created_by_name(self, obj):
        """Get creator name"""
        return obj.created_by.get_full_name() or obj.created_by.username

    def create(self, validated_data):
        """Create credential with encryption"""
        credential_data = validated_data.pop('credential_data', {})

        credential = super().create(validated_data)

        # Encrypt and store credential data
        if credential_data:
            credential.set_encrypted_data(credential_data)
            credential.save()

        return credential

    def update(self, instance, validated_data):
        """Update credential with encryption"""
        credential_data = validated_data.pop('credential_data', None)

        instance = super().update(instance, validated_data)

        # Update encrypted data if provided
        if credential_data is not None:
            instance.set_encrypted_data(credential_data)
            instance.save()

        return instance


class NodeCredentialTestSerializer(serializers.Serializer):
    """
    Credential testing result serializer
    """

    status = serializers.ChoiceField(choices=['success', 'error'])
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class NodeExecutionLogSerializer(serializers.ModelSerializer):
    """
    Node execution log serializer
    """

    node_type_name = serializers.CharField(source='node_type.display_name', read_only=True)
    workflow_name = serializers.CharField(source='execution.workflow.name', read_only=True)
    duration_ms = serializers.ReadOnlyField()

    class Meta:
        model = NodeExecutionLog
        fields = [
            'id', 'node_id', 'node_type_name', 'node_name', 'workflow_name',
            'status', 'started_at', 'completed_at', 'execution_time',
            'duration_ms', 'input_data', 'output_data', 'error_message',
            'error_type', 'error_details', 'stack_trace', 'memory_usage_mb',
            'cpu_usage_percent', 'network_requests', 'retry_count', 'is_retry'
        ]
        read_only_fields = fields


class NodeTypeRatingSerializer(serializers.ModelSerializer):
    """
    Node type rating serializer
    """

    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = NodeTypeRating
        fields = [
            'id', 'rating', 'review', 'user_name', 'organization_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_name', 'organization_name', 'created_at', 'updated_at']

    def validate_rating(self, value):
        """Validate rating value"""
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value


class CustomNodeTypeSerializer(serializers.ModelSerializer):
    """
    Custom node type serializer
    """

    base_node_name = serializers.CharField(source='base_node_type.display_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    shared_with_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomNodeType
        fields = [
            'id', 'name', 'display_name', 'description', 'base_node_name',
            'custom_properties', 'custom_code', 'visibility', 'version',
            'is_active', 'created_by_name', 'created_at', 'updated_at',
            'shared_with_count'
        ]
        read_only_fields = [
            'id', 'created_by_name', 'created_at', 'updated_at', 'shared_with_count'
        ]

    def get_shared_with_count(self, obj):
        """Get count of organizations this is shared with"""
        return obj.shared_with_orgs.count()

    def validate_custom_code(self, value):
        """Validate custom code for security"""
        if value:
            # Basic security checks
            dangerous_keywords = [
                'import os', 'import subprocess', 'import sys',
                'exec', 'eval', '__import__', 'open(',
                'file(', 'input(', 'raw_input('
            ]

            for keyword in dangerous_keywords:
                if keyword in value:
                    raise serializers.ValidationError(
                        f"Dangerous keyword '{keyword}' not allowed in custom code"
                    )

        return value


class NodeTypeInstallationSerializer(serializers.ModelSerializer):
    """
    Node type installation serializer
    """

    node_type = NodeTypeSerializer(read_only=True)
    installed_by_name = serializers.CharField(source='installed_by.get_full_name', read_only=True)

    class Meta:
        model = NodeTypeInstallation
        fields = [
            'id', 'node_type', 'installed_version', 'is_enabled',
            'default_config', 'installed_by_name', 'installed_at', 'last_updated'
        ]
        read_only_fields = [
            'id', 'installed_by_name', 'installed_at', 'last_updated'
        ]


class NodeInstallationSerializer(serializers.ModelSerializer):
    """
    Simplified node installation serializer
    """

    node_name = serializers.CharField(source='node_type.name', read_only=True)
    display_name = serializers.CharField(source='node_type.display_name', read_only=True)
    category = serializers.CharField(source='node_type.category.name', read_only=True)
    icon = serializers.CharField(source='node_type.icon', read_only=True)
    color = serializers.CharField(source='node_type.color', read_only=True)

    class Meta:
        model = NodeTypeInstallation
        fields = [
            'id', 'node_name', 'display_name', 'category', 'icon', 'color',
            'installed_version', 'is_enabled', 'installed_at'
        ]


class NodeSchemaSerializer(serializers.Serializer):
    """
    Node schema validation serializer
    """

    properties_schema = serializers.JSONField()
    inputs_schema = serializers.ListField()
    outputs_schema = serializers.ListField()

    def validate_properties_schema(self, value):
        """Validate JSON schema format"""
        import jsonschema

        try:
            # Validate that it's a valid JSON schema
            jsonschema.validators.validator_for(value).check_schema(value)
            return value
        except jsonschema.SchemaError as e:
            raise serializers.ValidationError(f"Invalid JSON schema: {str(e)}")

    def validate_inputs_schema(self, value):
        """Validate inputs schema"""
        for i, input_def in enumerate(value):
            if not isinstance(input_def, dict):
                raise serializers.ValidationError(f"Input {i} must be an object")

            if 'name' not in input_def:
                raise serializers.ValidationError(f"Input {i} missing 'name' field")

            if 'type' not in input_def:
                input_def['type'] = 'any'  # Default type

        return value

    def validate_outputs_schema(self, value):
        """Validate outputs schema"""
        for i, output_def in enumerate(value):
            if not isinstance(output_def, dict):
                raise serializers.ValidationError(f"Output {i} must be an object")

            if 'name' not in output_def:
                raise serializers.ValidationError(f"Output {i} missing 'name' field")

            if 'type' not in output_def:
                output_def['type'] = 'any'  # Default type

        return value


class NodeExecutionSerializer(serializers.Serializer):
    """
    Node execution request serializer
    """

    input_data = serializers.JSONField(default=dict)
    configuration = serializers.JSONField(default=dict)
    timeout = serializers.IntegerField(min_value=1, max_value=300, required=False)

    def validate_configuration(self, value):
        """Validate node configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Configuration must be an object")
        return value


class NodePerformanceSerializer(serializers.Serializer):
    """
    Node performance metrics serializer
    """

    node_type = serializers.CharField()
    total_executions = serializers.IntegerField()
    successful_executions = serializers.IntegerField()
    failed_executions = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_execution_time = serializers.FloatField()
    min_execution_time = serializers.FloatField()
    max_execution_time = serializers.FloatField()
    last_execution = serializers.DateTimeField()


class NodeErrorAnalysisSerializer(serializers.Serializer):
    """
    Node error analysis serializer
    """

    error_type = serializers.CharField()
    error_count = serializers.IntegerField()
    last_occurrence = serializers.DateTimeField()
    affected_workflows = serializers.IntegerField()
    sample_error_message = serializers.CharField()


class NodeMarketplaceStatsSerializer(serializers.Serializer):
    """
    Node marketplace statistics serializer
    """

    total_nodes = serializers.IntegerField()
    categories = serializers.IntegerField()
    installations = serializers.IntegerField()
    average_rating = serializers.FloatField()
    top_categories = serializers.ListField(
        child=serializers.DictField()
    )
    featured_nodes = serializers.ListField(
        child=NodeTypeSerializer()
    )


class BulkNodeInstallSerializer(serializers.Serializer):
    """
    Bulk node installation serializer
    """

    node_type_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50
    )

    def validate_node_type_ids(self, value):
        """Validate node type IDs exist"""
        existing_ids = set(
            NodeType.objects.filter(
                id__in=value,
                is_active=True
            ).values_list('id', flat=True)
        )

        invalid_ids = set(value) - existing_ids
        if invalid_ids:
            raise serializers.ValidationError(
                f"Invalid node type IDs: {list(invalid_ids)}"
            )

        return value


class NodeExportSerializer(serializers.Serializer):
    """
    Node export serializer
    """

    include_credentials = serializers.BooleanField(default=False)
    include_custom_nodes = serializers.BooleanField(default=True)
    format = serializers.ChoiceField(choices=['json', 'yaml'], default='json')


class NodeImportSerializer(serializers.Serializer):
    """
    Node import serializer
    """

    data = serializers.JSONField()
    overwrite_existing = serializers.BooleanField(default=False)
    import_credentials = serializers.BooleanField(default=False)

    def validate_data(self, value):
        """Validate import data structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Import data must be an object")

        required_fields = ['nodes', 'version']
        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(f"Missing required field: {field}")

        return value