"""
Webhook models for advanced webhook management
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.utils import timezone
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
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_webhooks')

    # Statistics
    total_deliveries = models.IntegerField(default=0)
    successful_deliveries = models.IntegerField(default=0)
    failed_deliveries = models.IntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_endpoints'
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['url_path']),
            models.Index(fields=['workflow']),
        ]

    def __str__(self):
        return f"{self.name} - {self.organization.name}"

    def generate_url_path(self):
        """Generate unique URL path for webhook"""
        import secrets
        self.url_path = secrets.token_urlsafe(16)

    def verify_signature(self, payload, signature):
        """Verify webhook signature"""
        if self.authentication_type != 'signature':
            return True

        if not self.secret_token:
            return False

        expected_signature = hmac.new(
            self.secret_token.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    def update_delivery_stats(self, success=True):
        """Update delivery statistics"""
        self.total_deliveries += 1
        if success:
            self.successful_deliveries += 1
        else:
            self.failed_deliveries += 1
        self.last_triggered_at = timezone.now()
        self.save(update_fields=[
            'total_deliveries', 'successful_deliveries',
            'failed_deliveries', 'last_triggered_at'
        ])


class WebhookDelivery(models.Model):
    """
    Track webhook delivery attempts and responses
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')

    # Delivery identification
    delivery_id = models.CharField(max_length=255, unique=True)
    trigger_event = models.CharField(max_length=100)

    # Request details
    request_method = models.CharField(max_length=10, default='POST')
    request_headers = models.JSONField(default=dict)
    request_body = models.TextField()

    # Response details
    response_status_code = models.IntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=dict)
    response_body = models.TextField(blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)

    # Delivery status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    attempt_number = models.IntegerField(default=1)
    max_attempts = models.IntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'webhook_deliveries'
        indexes = [
            models.Index(fields=['webhook_endpoint', 'status']),
            models.Index(fields=['delivery_id']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Delivery {self.delivery_id} - {self.status}"

    def mark_delivered(self, status_code, response_body, response_time_ms, headers=None):
        """Mark delivery as successful"""
        self.status = 'delivered'
        self.response_status_code = status_code
        self.response_body = response_body
        self.response_time_ms = response_time_ms
        self.sent_at = timezone.now()

        if headers:
            self.response_headers = headers

        self.save()
        self.webhook_endpoint.update_delivery_stats(success=True)

    def mark_failed(self, status_code=None, response_body='', error_message=''):
        """Mark delivery as failed"""
        self.status = 'failed'
        self.response_status_code = status_code
        self.response_body = response_body or error_message
        self.sent_at = timezone.now()

        # Schedule retry if attempts remaining
        if self.attempt_number < self.max_attempts:
            retry_delay = self.webhook_endpoint.retry_delay * self.attempt_number
            self.next_retry_at = timezone.now() + timezone.timedelta(seconds=retry_delay)
            self.status = 'retrying'

        self.save()

        if self.status == 'failed':
            self.webhook_endpoint.update_delivery_stats(success=False)

    def can_retry(self):
        """Check if delivery can be retried"""
        return (
            self.status == 'retrying' and
            self.attempt_number < self.max_attempts and
            self.next_retry_at and
            self.next_retry_at <= timezone.now()
        )


class WebhookRateLimit(models.Model):
    """
    Rate limiting for webhook endpoints
    """

    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='rate_limits')
    ip_address = models.GenericIPAddressField()

    request_count = models.IntegerField(default=0)
    window_start = models.DateTimeField(default=timezone.now)
    is_blocked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_rate_limits'
        unique_together = ['webhook_endpoint', 'ip_address']
        indexes = [
            models.Index(fields=['webhook_endpoint', 'ip_address']),
            models.Index(fields=['window_start']),
        ]

    def __str__(self):
        return f"Rate limit for {self.ip_address} on {self.webhook_endpoint.name}"

    def check_rate_limit(self):
        """Check if request should be rate limited"""
        now = timezone.now()
        window_duration = timezone.timedelta(seconds=self.webhook_endpoint.rate_limit_window)

        # Reset window if expired
        if now - self.window_start > window_duration:
            self.window_start = now
            self.request_count = 0
            self.is_blocked = False

        # Increment request count
        self.request_count += 1

        # Check if limit exceeded
        if self.request_count > self.webhook_endpoint.rate_limit_requests:
            self.is_blocked = True

        self.save()
        return not self.is_blocked


class WebhookEvent(models.Model):
    """
    Webhook events for processing and auditing
    """

    EVENT_TYPES = [
        ('workflow_start', 'Workflow Started'),
        ('workflow_complete', 'Workflow Completed'),
        ('workflow_failed', 'Workflow Failed'),
        ('node_execute', 'Node Executed'),
        ('custom', 'Custom Event'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='events')

    # Event details
    name = models.CharField(max_length=255)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    event_data = models.JSONField(default=dict)

    # Processing status
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_time = models.DurationField(null=True, blank=True)

    # Results
    processing_result = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict)

    # Metadata
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook_events'
        indexes = [
            models.Index(fields=['webhook_endpoint', 'event_type']),
            models.Index(fields=['processed', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.name} - {self.event_type}"

    def mark_processed(self, result=None, error=None):
        """Mark event as processed"""
        self.processed = True
        self.processed_at = timezone.now()

        if self.created_at:
            self.processing_time = self.processed_at - self.created_at

        if result:
            self.processing_result = result

        if error:
            self.error_message = str(error)
            self.error_details = {'error': str(error)}

        self.save()


class WebhookTemplate(models.Model):
    """
    Templates for common webhook configurations
    """

    WEBHOOK_TYPES = [
        ('github', 'GitHub'),
        ('slack', 'Slack'),
        ('discord', 'Discord'),
        ('teams', 'Microsoft Teams'),
        ('generic', 'Generic HTTP'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webhook_templates')

    # Template details
    name = models.CharField(max_length=255)
    description = models.TextField()
    webhook_type = models.CharField(max_length=50, choices=WEBHOOK_TYPES)

    # Configuration
    default_config = models.JSONField(default=dict)
    example_payload = models.JSONField(default=dict)

    # Documentation
    setup_instructions = models.TextField(blank=True)
    validation_rules = models.JSONField(default=dict)

    # Metadata
    is_active = models.BooleanField(default=True)
    usage_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_templates'
        indexes = [
            models.Index(fields=['webhook_type', 'is_active']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} ({self.webhook_type})"

    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])