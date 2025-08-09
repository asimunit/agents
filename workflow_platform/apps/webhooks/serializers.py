"""
Webhook Serializers
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    WebhookEndpoint, WebhookDelivery, WebhookEvent,
    WebhookTemplate, WebhookRateLimit
)
from apps.workflows.models import Workflow


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """
    Webhook endpoint serializer
    """

    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    full_url = serializers.ReadOnlyField()
    success_rate = serializers.ReadOnlyField()

    class Meta:
        model = WebhookEndpoint
        fields = [
            'id', 'name', 'description', 'url_path', 'full_url', 'workflow',
            'workflow_name', 'authentication_type', 'allowed_methods',
            'allowed_ips', 'custom_headers', 'rate_limit_requests',
            'rate_limit_window', 'timeout_seconds', 'retry_attempts',
            'retry_delay', 'data_format', 'status', 'is_public',
            'total_requests', 'successful_requests', 'failed_requests',
            'success_rate', 'last_triggered_at', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'url_path', 'full_url', 'workflow_name', 'total_requests',
            'successful_requests', 'failed_requests', 'success_rate',
            'last_triggered_at', 'created_by_name', 'created_at', 'updated_at'
        ]


class WebhookEndpointCreateSerializer(serializers.ModelSerializer):
    """
    Webhook endpoint creation serializer
    """

    workflow_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = [
            'name', 'description', 'workflow_id', 'authentication_type',
            'secret_token', 'signature_header', 'allowed_methods',
            'allowed_ips', 'custom_headers', 'rate_limit_requests',
            'rate_limit_window', 'timeout_seconds', 'retry_attempts',
            'retry_delay', 'data_format', 'status', 'is_public'
        ]

    def validate_workflow_id(self, value):
        """Validate workflow belongs to organization"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            workflow = Workflow.objects.get(id=value, organization=organization)
            return workflow
        except Workflow.DoesNotExist:
            raise serializers.ValidationError("Workflow not found or access denied")

    def validate_allowed_methods(self, value):
        """Validate HTTP methods"""
        if not value:
            return ['POST']  # Default to POST

        valid_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
        for method in value:
            if method not in valid_methods:
                raise serializers.ValidationError(f"Invalid HTTP method: {method}")

        return value

    def validate_allowed_ips(self, value):
        """Validate IP addresses and CIDR blocks"""
        if not value:
            return value

        import ipaddress

        for ip_entry in value:
            try:
                if '/' in ip_entry:
                    ipaddress.ip_network(ip_entry, strict=False)
                else:
                    ipaddress.ip_address(ip_entry)
            except ValueError:
                raise serializers.ValidationError(f"Invalid IP address or CIDR: {ip_entry}")

        return value

    def validate_rate_limit_requests(self, value):
        """Validate rate limit"""
        if value < 1 or value > 10000:
            raise serializers.ValidationError("Rate limit must be between 1 and 10000 requests")
        return value

    def validate_secret_token(self, value):
        """Validate secret token"""
        if self.initial_data.get('authentication_type') in ['secret', 'bearer', 'signature']:
            if not value:
                raise serializers.ValidationError("Secret token is required for this authentication type")

            if len(value) < 16:
                raise serializers.ValidationError("Secret token must be at least 16 characters long")

        return value

    def create(self, validated_data):
        """Create webhook endpoint"""
        workflow = validated_data.pop('workflow_id')
        validated_data['workflow'] = workflow

        return super().create(validated_data)


class WebhookDeliverySerializer(serializers.ModelSerializer):
    """
    Webhook delivery serializer
    """

    webhook_name = serializers.CharField(source='webhook_endpoint.name', read_only=True)
    workflow_name = serializers.CharField(source='webhook_endpoint.workflow.name', read_only=True)
    duration_ms = serializers.SerializerMethodField()

    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'webhook_name', 'workflow_name', 'http_method', 'ip_address',
            'user_agent', 'status', 'workflow_execution_id', 'response_status_code',
            'error_message', 'retry_count', 'received_at', 'processed_at',
            'processing_time_ms', 'duration_ms'
        ]
        read_only_fields = fields

    def get_duration_ms(self, obj):
        """Get processing duration in milliseconds"""
        if obj.received_at and obj.processed_at:
            return int((obj.processed_at - obj.received_at).total_seconds() * 1000)
        return None


class WebhookDeliveryDetailSerializer(WebhookDeliverySerializer):
    """
    Detailed webhook delivery serializer with payload data
    """

    class Meta(WebhookDeliverySerializer.Meta):
        fields = WebhookDeliverySerializer.Meta.fields + [
            'headers', 'payload', 'raw_payload', 'response_headers',
            'response_body', 'error_details'
        ]


class WebhookEventSerializer(serializers.ModelSerializer):
    """
    Webhook event serializer
    """

    webhook_name = serializers.CharField(source='webhook_endpoint.name', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'webhook_name', 'event_type', 'description', 'user_name',
            'ip_address', 'user_agent', 'event_data', 'created_at'
        ]
        read_only_fields = fields


class WebhookTemplateSerializer(serializers.ModelSerializer):
    """
    Webhook template serializer
    """

    class Meta:
        model = WebhookTemplate
        fields = [
            'id', 'name', 'description', 'category', 'service_name',
            'service_icon', 'documentation_url', 'configuration',
            'example_payload', 'usage_count', 'is_featured', 'is_official',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class WebhookAnalyticsSerializer(serializers.Serializer):
    """
    Webhook analytics data serializer
    """

    overview = serializers.DictField()
    daily_stats = serializers.ListField(child=serializers.DictField())
    error_analysis = serializers.ListField(child=serializers.DictField())
    top_source_ips = serializers.ListField(child=serializers.DictField())
    performance_metrics = serializers.DictField(required=False)


class WebhookRateLimitSerializer(serializers.ModelSerializer):
    """
    Webhook rate limit serializer
    """

    class Meta:
        model = WebhookRateLimit
        fields = [
            'ip_address', 'request_count', 'window_start', 'last_request',
            'is_blocked', 'blocked_until'
        ]
        read_only_fields = fields


class WebhookTestSerializer(serializers.Serializer):
    """
    Webhook test request serializer
    """

    payload = serializers.JSONField(default=dict)
    headers = serializers.DictField(default=dict, required=False)
    method = serializers.ChoiceField(
        choices=['GET', 'POST', 'PUT', 'PATCH'],
        default='POST'
    )

    def validate_payload(self, value):
        """Validate test payload"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Payload must be an object")
        return value


class WebhookBulkOperationSerializer(serializers.Serializer):
    """
    Bulk webhook operations serializer
    """

    webhook_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50
    )
    operation = serializers.ChoiceField(choices=[
        'activate', 'deactivate', 'delete', 'regenerate_urls'
    ])

    def validate_webhook_ids(self, value):
        """Validate webhook IDs belong to organization"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        existing_ids = set(
            WebhookEndpoint.objects.filter(
                id__in=value,
                organization=organization
            ).values_list('id', flat=True)
        )

        invalid_ids = set(value) - existing_ids
        if invalid_ids:
            raise serializers.ValidationError(
                f"Invalid webhook IDs: {list(invalid_ids)}"
            )

        return value


class WebhookImportSerializer(serializers.Serializer):
    """
    Webhook import serializer
    """

    webhooks = serializers.ListField(child=serializers.DictField())
    overwrite_existing = serializers.BooleanField(default=False)

    def validate_webhooks(self, value):
        """Validate webhook import data"""
        required_fields = ['name', 'workflow_id', 'authentication_type']

        for i, webhook_data in enumerate(value):
            for field in required_fields:
                if field not in webhook_data:
                    raise serializers.ValidationError(
                        f"Webhook {i}: Missing required field '{field}'"
                    )

        return value


class WebhookExportSerializer(serializers.Serializer):
    """
    Webhook export serializer
    """

    include_credentials = serializers.BooleanField(default=False)
    include_analytics = serializers.BooleanField(default=False)
    format = serializers.ChoiceField(choices=['json', 'yaml'], default='json')


class WebhookStatisticsSerializer(serializers.Serializer):
    """
    Webhook statistics serializer
    """

    total_webhooks = serializers.IntegerField()
    active_webhooks = serializers.IntegerField()
    total_deliveries = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_processing_time = serializers.FloatField()

    # Time-based statistics
    deliveries_today = serializers.IntegerField()
    deliveries_this_week = serializers.IntegerField()
    deliveries_this_month = serializers.IntegerField()

    # Top performing webhooks
    top_webhooks = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )


class WebhookSecuritySerializer(serializers.Serializer):
    """
    Webhook security configuration serializer
    """

    enable_ip_whitelist = serializers.BooleanField(default=False)
    allowed_ips = serializers.ListField(
        child=serializers.IPAddressField(),
        required=False
    )
    enable_rate_limiting = serializers.BooleanField(default=True)
    rate_limit_requests = serializers.IntegerField(min_value=1, max_value=10000)
    rate_limit_window = serializers.IntegerField(min_value=60, max_value=86400)

    # Authentication settings
    require_authentication = serializers.BooleanField(default=True)
    authentication_type = serializers.ChoiceField(choices=[
        'none', 'secret', 'signature', 'basic', 'bearer'
    ])

    # Security headers
    require_https = serializers.BooleanField(default=True)
    custom_headers = serializers.DictField(default=dict)


class WebhookMonitoringSerializer(serializers.Serializer):
    """
    Webhook monitoring configuration serializer
    """

    enable_monitoring = serializers.BooleanField(default=True)
    alert_on_failures = serializers.BooleanField(default=True)
    failure_threshold = serializers.IntegerField(min_value=1, max_value=100, default=5)
    alert_email = serializers.EmailField(required=False)

    # Performance monitoring
    enable_performance_alerts = serializers.BooleanField(default=False)
    performance_threshold_ms = serializers.IntegerField(default=5000)

    # Retention settings
    log_retention_days = serializers.IntegerField(min_value=1, max_value=365, default=30)


class WebhookResponseSerializer(serializers.Serializer):
    """
    Webhook response serializer for API responses
    """

    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField(required=False)
    errors = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )


class WebhookValidationSerializer(serializers.Serializer):
    """
    Webhook validation result serializer
    """

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