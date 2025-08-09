"""
Webhook models for advanced webhook management
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from apps.organizations.models import Organization
from apps.workflows.models import Workflow
import uuid
import hashlib
import hmac


class WebhookEndpoint(models.Model):
    """
    Webhook endpoints for triggering workflows
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('paused', 'Paused'),
    ]

    AUTHENTICATION_CHOICES = [
        ('none', 'None'),
        ('secret', 'Secret Token'),
        ('signature', 'HMAC Signature'),
        ('basic', 'Basic Auth'),
        ('bearer', 'Bearer Token'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='webhook_endpoints')
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='webhook_endpoints')

    # Endpoint configuration
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url_path = models.CharField(max_length=255, unique=True)  # /webhooks/{url_path}

    # Authentication
    authentication_type = models.CharField(max_length=20, choices=AUTHENTICATION_CHOICES, default='none')
    secret_token = models.CharField(max_length=255, blank=True)
    signature_header = models.CharField(max_length=100, default='X-Hub-Signature-256')

    # HTTP Configuration
    allowed_methods = models.JSONField(default=list)  # ['POST', 'PUT']
    allowed_ips = models.JSONField(default=list, blank=True)  # IP whitelist
    custom_headers = models.JSONField(default=dict, blank=True)  # Required headers

    # Rate limiting
    rate_limit_requests = models.IntegerField(default=100)  # requests per hour
    rate_limit_window = models.IntegerField(default=3600)  # seconds

    # Processing configuration
    timeout_seconds = models.IntegerField(default=30)
    retry_attempts = models.IntegerField(default=3)
    retry_delay = models.IntegerField(default=60)  # seconds

    # Data processing
    data_format = models.CharField(max_length=20, choices=[
        ('json', 'JSON'),
        ('form', 'Form Data'),
        ('xml', 'XML'),
        ('raw', 'Raw'),
    ], default='json')

    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_public = models.BooleanField(default=False)

    # Statistics
    total_requests = models.IntegerField(default=0)
    successful_requests = models.IntegerField(default=0)
    failed_requests = models.IntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_webhooks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_endpoints'
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['url_path']),
            models.Index(fields=['workflow', 'status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.url_path})"

    @property
    def success_rate(self):
        """Calculate webhook success rate"""
        if self.total_requests == 0:
            return 0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def full_url(self):
        """Get full webhook URL"""
        from django.conf import settings
        base_url = getattr(settings, 'WEBHOOK_BASE_URL', 'https://api.workflowplatform.com')
        return f"{base_url}/webhooks/{self.url_path}"

    def verify_signature(self, payload, signature, secret=None):
        """Verify HMAC signature"""
        if self.authentication_type != 'signature':
            return True

        secret = secret or self.secret_token
        if not secret:
            return False

        # Calculate expected signature
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures
        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    def is_ip_allowed(self, ip_address):
        """Check if IP address is allowed"""
        if not self.allowed_ips:
            return True

        import ipaddress

        try:
            ip = ipaddress.ip_address(ip_address)
            for allowed_ip in self.allowed_ips:
                if '/' in allowed_ip:
                    # CIDR notation
                    if ip in ipaddress.ip_network(allowed_ip):
                        return True
                else:
                    # Single IP
                    if ip == ipaddress.ip_address(allowed_ip):
                        return True
            return False
        except ValueError:
            return False

    def increment_stats(self, success=True):
        """Increment webhook statistics"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        from django.utils import timezone
        self.last_triggered_at = timezone.now()
        self.save(update_fields=['total_requests', 'successful_requests', 'failed_requests', 'last_triggered_at'])


class WebhookDelivery(models.Model):
    """
    Individual webhook delivery attempts
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('retry', 'Retry'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')

    # Request details
    http_method = models.CharField(max_length=10)
    headers = models.JSONField(default=dict)
    payload = models.JSONField(default=dict)
    raw_payload = models.TextField(blank=True)

    # Client information
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)

    # Processing details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    workflow_execution_id = models.UUIDField(null=True, blank=True)

    # Response details
    response_status_code = models.IntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.TextField(blank=True)

    # Error handling
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    retry_count = models.IntegerField(default=0)

    # Timing
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'webhook_deliveries'
        indexes = [
            models.Index(fields=['webhook_endpoint', 'status']),
            models.Index(fields=['received_at']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['workflow_execution_id']),
        ]
        ordering = ['-received_at']

    def __str__(self):
        return f"Delivery {self.id} - {self.webhook_endpoint.name} ({self.status})"

    def mark_processing(self):
        """Mark delivery as processing"""
        self.status = 'processing'
        self.save(update_fields=['status'])

    def mark_success(self, execution_id=None):
        """Mark delivery as successful"""
        from django.utils import timezone

        self.status = 'success'
        self.processed_at = timezone.now()
        if execution_id:
            self.workflow_execution_id = execution_id

        if self.received_at and self.processed_at:
            self.processing_time_ms = int((self.processed_at - self.received_at).total_seconds() * 1000)

        self.save(update_fields=['status', 'processed_at', 'workflow_execution_id', 'processing_time_ms'])

    def mark_failed(self, error_message, error_details=None):
        """Mark delivery as failed"""
        from django.utils import timezone

        self.status = 'failed'
        self.processed_at = timezone.now()
        self.error_message = error_message

        if error_details:
            self.error_details = error_details

        if self.received_at and self.processed_at:
            self.processing_time_ms = int((self.processed_at - self.received_at).total_seconds() * 1000)

        self.save(update_fields=['status', 'processed_at', 'error_message', 'error_details', 'processing_time_ms'])


class WebhookRateLimit(models.Model):
    """
    Rate limiting tracking for webhooks
    """

    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='rate_limits')
    ip_address = models.GenericIPAddressField()

    # Rate limiting
    request_count = models.IntegerField(default=0)
    window_start = models.DateTimeField(auto_now_add=True)
    last_request = models.DateTimeField(auto_now=True)

    # Blocking
    is_blocked = models.BooleanField(default=False)
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'webhook_rate_limits'
        unique_together = ['webhook_endpoint', 'ip_address']
        indexes = [
            models.Index(fields=['webhook_endpoint', 'ip_address']),
            models.Index(fields=['window_start']),
            models.Index(fields=['is_blocked', 'blocked_until']),
        ]

    def is_rate_limited(self):
        """Check if requests are rate limited"""
        from django.utils import timezone

        now = timezone.now()

        # Check if blocked
        if self.is_blocked and self.blocked_until and now < self.blocked_until:
            return True

        # Reset window if expired
        window_duration = timezone.timedelta(seconds=self.webhook_endpoint.rate_limit_window)
        if now - self.window_start > window_duration:
            self.request_count = 0
            self.window_start = now
            self.is_blocked = False
            self.blocked_until = None
            self.save()

        # Check rate limit
        return self.request_count >= self.webhook_endpoint.rate_limit_requests

    def increment_request(self):
        """Increment request count"""
        from django.utils import timezone

        self.request_count += 1
        self.last_request = timezone.now()

        # Block if rate limit exceeded
        if self.request_count >= self.webhook_endpoint.rate_limit_requests:
            self.is_blocked = True
            self.blocked_until = timezone.now() + timezone.timedelta(
                seconds=self.webhook_endpoint.rate_limit_window
            )

        self.save()


class WebhookEvent(models.Model):
    """
    Webhook events for audit logging
    """

    EVENT_TYPES = [
        ('endpoint_created', 'Endpoint Created'),
        ('endpoint_updated', 'Endpoint Updated'),
        ('endpoint_deleted', 'Endpoint Deleted'),
        ('delivery_received', 'Delivery Received'),
        ('delivery_processed', 'Delivery Processed'),
        ('delivery_failed', 'Delivery Failed'),
        ('rate_limit_hit', 'Rate Limit Hit'),
        ('authentication_failed', 'Authentication Failed'),
        ('ip_blocked', 'IP Blocked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='webhook_events')
    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='events', null=True,
                                         blank=True)
    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.CASCADE, related_name='events', null=True,
                                 blank=True)

    # Event details
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    description = models.TextField()

    # Context
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Additional data
    event_data = models.JSONField(default=dict, blank=True)

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook_events'
        indexes = [
            models.Index(fields=['organization', 'event_type']),
            models.Index(fields=['webhook_endpoint', 'event_type']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - {self.webhook_endpoint.name if self.webhook_endpoint else 'N/A'}"


class WebhookTemplate(models.Model):
    """
    Webhook templates for common integrations
    """

    CATEGORY_CHOICES = [
        ('ecommerce', 'E-commerce'),
        ('payment', 'Payment'),
        ('communication', 'Communication'),
        ('analytics', 'Analytics'),
        ('social', 'Social Media'),
        ('development', 'Development'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Template details
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)

    # Service information
    service_name = models.CharField(max_length=100)  # e.g., 'Stripe', 'GitHub', 'Shopify'
    service_icon = models.CharField(max_length=50, blank=True)
    documentation_url = models.URLField(blank=True)

    # Configuration template
    configuration = models.JSONField(default=dict)
    example_payload = models.JSONField(default=dict)

    # Usage
    usage_count = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    is_official = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_templates'
        indexes = [
            models.Index(fields=['category', 'is_featured']),
            models.Index(fields=['service_name']),
            models.Index(fields=['usage_count']),
        ]

    def __str__(self):
        return f"{self.service_name} - {self.name}"

    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])