"""
Webhook Serializers - API serialization for webhook management
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    WebhookEndpoint, WebhookDelivery, WebhookRateLimit,
    WebhookEvent, WebhookTemplate
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


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """Webhook endpoint serializer"""

    workflow = WorkflowBasicSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    full_url = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEndpoint
        fields = [
            'id', 'name', 'description', 'workflow', 'url_path', 'full_url',
            'status', 'authentication_type', 'allowed_methods', 'allowed_ips',
            'custom_headers', 'rate_limit_requests', 'rate_limit_window',
            'timeout_seconds', 'retry_attempts', 'retry_delay', 'data_format',
            'total_deliveries', 'successful_deliveries', 'failed_deliveries',
            'last_triggered_at', 'success_rate', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'url_path', 'full_url', 'total_deliveries', 'successful_deliveries',
            'failed_deliveries', 'last_triggered_at', 'success_rate', 'created_by',
            'created_at', 'updated_at'
        ]

    def get_full_url(self, obj):
        """Get full webhook URL"""
        request = self.context.get('request')
        if request:
            base_url = f"{request.scheme}://{request.get_host()}"
            return f"{base_url}/webhooks/{obj.url_path}/"
        return f"/webhooks/{obj.url_path}/"

    def get_success_rate(self, obj):
        """Calculate success rate"""
        if obj.total_deliveries > 0:
            return round((obj.successful_deliveries / obj.total_deliveries) * 100, 2)
        return 0


class WebhookEndpointCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating webhook endpoints"""

    workflow_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = [
            'name', 'description', 'workflow_id', 'authentication_type',
            'secret_token', 'signature_header', 'allowed_methods', 'allowed_ips',
            'custom_headers', 'rate_limit_requests', 'rate_limit_window',
            'timeout_seconds', 'retry_attempts', 'retry_delay', 'data_format'
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

    def validate_allowed_methods(self, value):
        """Validate allowed HTTP methods"""
        if not value:
            return ['POST']  # Default to POST

        valid_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
        for method in value:
            if method.upper() not in valid_methods:
                raise serializers.ValidationError(f"Invalid HTTP method: {method}")

        return [method.upper() for method in value]

    def validate_allowed_ips(self, value):
        """Validate IP addresses"""
        if not value:
            return []

        import ipaddress
        for ip in value:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                try:
                    ipaddress.ip_network(ip, strict=False)
                except ValueError:
                    raise serializers.ValidationError(f"Invalid IP address or network: {ip}")

        return value

    def create(self, validated_data):
        """Create webhook endpoint"""
        workflow = validated_data.pop('workflow_id')
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        webhook = WebhookEndpoint.objects.create(
            organization=organization,
            workflow=workflow,
            created_by=request.user,
            **validated_data
        )

        # Generate unique URL path
        webhook.generate_url_path()
        webhook.save()

        return webhook


class WebhookDeliverySerializer(serializers.ModelSerializer):
    """Webhook delivery serializer"""

    webhook_endpoint = WebhookEndpointSerializer(read_only=True)
    duration = serializers.SerializerMethodField()
    can_retry = serializers.ReadOnlyField()

    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'webhook_endpoint', 'delivery_id', 'trigger_event',
            'request_method', 'request_headers', 'request_body',
            'response_status_code', 'response_headers', 'response_body',
            'response_time_ms', 'status', 'attempt_number', 'max_attempts',
            'next_retry_at', 'duration', 'can_retry', 'created_at', 'sent_at'
        ]
        read_only_fields = fields

    def get_duration(self, obj):
        """Calculate delivery duration"""
        if obj.sent_at and obj.created_at:
            delta = obj.sent_at - obj.created_at
            return delta.total_seconds()
        return None


class WebhookRateLimitSerializer(serializers.ModelSerializer):
    """Webhook rate limit serializer"""

    webhook_endpoint = WebhookEndpointSerializer(read_only=True)
    time_remaining = serializers.SerializerMethodField()

    class Meta:
        model = WebhookRateLimit
        fields = [
            'id', 'webhook_endpoint', 'ip_address', 'request_count',
            'window_start', 'is_blocked', 'time_remaining',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_time_remaining(self, obj):
        """Calculate time remaining in current window"""
        from django.utils import timezone
        window_duration = timezone.timedelta(seconds=obj.webhook_endpoint.rate_limit_window)
        window_end = obj.window_start + window_duration
        remaining = window_end - timezone.now()

        if remaining.total_seconds() > 0:
            return remaining.total_seconds()
        return 0


class WebhookEventSerializer(serializers.ModelSerializer):
    """Webhook event serializer"""

    webhook_endpoint = WebhookEndpointSerializer(read_only=True)
    processing_time_seconds = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'webhook_endpoint', 'name', 'event_type', 'event_data',
            'processed', 'processed_at', 'processing_time', 'processing_time_seconds',
            'processing_result', 'error_message', 'error_details',
            'metadata', 'created_at'
        ]
        read_only_fields = [
            'id', 'processed_at', 'processing_time', 'processing_time_seconds',
            'processing_result', 'error_message', 'error_details', 'created_at'
        ]

    def get_processing_time_seconds(self, obj):
        """Get processing time in seconds"""
        if obj.processing_time:
            return obj.processing_time.total_seconds()
        return None


class WebhookEventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating webhook events"""

    webhook_endpoint_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = WebhookEvent
        fields = [
            'webhook_endpoint_id', 'name', 'event_type', 'event_data', 'metadata'
        ]

    def validate_webhook_endpoint_id(self, value):
        """Validate webhook endpoint exists and user has access"""
        request = self.context['request']
        organization = request.user.organization_memberships.first().organization

        try:
            webhook = WebhookEndpoint.objects.get(
                id=value,
                organization=organization
            )
            return webhook
        except WebhookEndpoint.DoesNotExist:
            raise serializers.ValidationError("Webhook endpoint not found or access denied")

    def create(self, validated_data):
        """Create webhook event"""
        webhook_endpoint = validated_data.pop('webhook_endpoint_id')

        event = WebhookEvent.objects.create(
            webhook_endpoint=webhook_endpoint,
            **validated_data
        )

        return event


class WebhookTemplateSerializer(serializers.ModelSerializer):
    """Webhook template serializer"""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = WebhookTemplate
        fields = [
            'id', 'name', 'description', 'webhook_type', 'default_config',
            'example_payload', 'setup_instructions', 'validation_rules',
            'is_active', 'usage_count', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'usage_count', 'created_by', 'created_at', 'updated_at'
        ]


class WebhookTemplateCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating webhook templates"""

    class Meta:
        model = WebhookTemplate
        fields = [
            'name', 'description', 'webhook_type', 'default_config',
            'example_payload', 'setup_instructions', 'validation_rules'
        ]

    def validate_default_config(self, value):
        """Validate default configuration"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Default config must be a JSON object")
        return value

    def validate_example_payload(self, value):
        """Validate example payload"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Example payload must be a JSON object")
        return value

    def create(self, validated_data):
        """Create webhook template"""
        request = self.context['request']

        template = WebhookTemplate.objects.create(
            created_by=request.user,
            **validated_data
        )

        return template


class WebhookStatsSerializer(serializers.Serializer):
    """Webhook statistics serializer"""

    total_endpoints = serializers.IntegerField()
    active_endpoints = serializers.IntegerField()
    total_deliveries = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_response_time = serializers.FloatField()

    # Trends
    daily_deliveries = serializers.ListField(
        child=serializers.DictField()
    )

    # Top endpoints
    top_endpoints = serializers.ListField(
        child=serializers.DictField()
    )


class WebhookTestSerializer(serializers.Serializer):
    """Serializer for webhook testing"""

    test_data = serializers.JSONField(default=dict)
    headers = serializers.JSONField(default=dict)

    def validate_test_data(self, value):
        """Validate test data"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Test data must be a JSON object")
        return value

    def validate_headers(self, value):
        """Validate headers"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Headers must be a JSON object")

        # Validate header names and values
        for key, val in value.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise serializers.ValidationError("Header names and values must be strings")

        return value