"""
Node models - Define node types and their configurations
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from apps.organizations.models import Organization
import uuid
import json


class NodeCategory(models.Model):
    """Categories for organizing node types"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default='#6366f1')
    sort_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'node_categories'
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Node Categories'

    def __str__(self):
        return self.display_name


class NodeType(models.Model):
    """Node type definitions - Core building blocks"""

    TYPE_CHOICES = [
        ('trigger', 'Trigger'),
        ('action', 'Action'),
        ('transform', 'Transform'),
        ('condition', 'Condition'),
        ('output', 'Output'),
    ]

    SOURCE_CHOICES = [
        ('built_in', 'Built-in'),
        ('community', 'Community'),
        ('custom', 'Custom'),
        ('premium', 'Premium'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Information
    name = models.CharField(
        max_length=100,
        unique=True,
        validators=[RegexValidator(r'^[a-z0-9_]+$', 'Only lowercase letters, numbers, and underscores allowed')]
    )
    display_name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.ForeignKey(NodeCategory, on_delete=models.CASCADE, related_name='node_types')

    # Node Classification
    node_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='action')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='built_in')

    # Visual Properties
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default='#6366f1')

    # Technical Configuration
    executor_class = models.CharField(max_length=255)  # Python class path
    schema_version = models.CharField(max_length=10, default='1.0')

    # Node Schema Definition
    properties_schema = models.JSONField(default=dict)  # JSON Schema for node properties
    inputs_schema = models.JSONField(default=list)  # Input port definitions
    outputs_schema = models.JSONField(default=list)  # Output port definitions

    # Execution Configuration
    default_timeout = models.IntegerField(default=30)  # seconds
    max_timeout = models.IntegerField(default=300)  # seconds
    supports_retry = models.BooleanField(default=True)
    supports_async = models.BooleanField(default=True)

    # Requirements & Dependencies
    required_credentials = models.JSONField(default=list)  # Required credential types
    required_packages = models.JSONField(default=list)  # Python packages
    minimum_plan = models.CharField(max_length=20, choices=Organization.PLAN_CHOICES, default='free')

    # Documentation
    documentation_url = models.URLField(blank=True)
    examples = models.JSONField(default=list)  # Example configurations

    # Marketplace & Distribution
    is_active = models.BooleanField(default=True)
    is_beta = models.BooleanField(default=False)
    version = models.CharField(max_length=20, default='1.0.0')

    # Publishing (for marketplace)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    repository_url = models.URLField(blank=True)
    license = models.CharField(max_length=50, default='MIT')

    # Usage Statistics
    usage_count = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    rating_count = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'node_types'
        indexes = [
            models.Index(fields=['node_type', 'is_active']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['source', 'is_active']),
            models.Index(fields=['usage_count', 'rating']),
        ]

    def __str__(self):
        return self.display_name

    def get_example_config(self):
        """Get the first example configuration"""
        if self.examples:
            return self.examples[0]
        return {}

    def validate_configuration(self, config):
        """Validate node configuration against schema"""
        import jsonschema

        try:
            jsonschema.validate(config, self.properties_schema)
            return True, []
        except jsonschema.ValidationError as e:
            return False, [str(e)]

    def get_input_ports(self):
        """Get formatted input port definitions"""
        return [
            {
                'name': port['name'],
                'type': port.get('type', 'any'),
                'required': port.get('required', False),
                'description': port.get('description', ''),
            }
            for port in self.inputs_schema
        ]

    def get_output_ports(self):
        """Get formatted output port definitions"""
        return [
            {
                'name': port['name'],
                'type': port.get('type', 'any'),
                'description': port.get('description', ''),
            }
            for port in self.outputs_schema
        ]

    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])


class NodeTypeCategory(models.Model):
    """Categories for organizing node types"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default='#4f46e5')  # Hex color

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'node_type_categories'
        verbose_name = 'Node Type Category'
        verbose_name_plural = 'Node Type Categories'

    def __str__(self):
        return self.name


class NodeTypeRating(models.Model):
    """Ratings for node types"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node_type = models.ForeignKey(NodeType, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='node_ratings')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='node_ratings')

    rating = models.IntegerField()  # 1-5 stars
    review = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'node_type_ratings'
        unique_together = ['node_type', 'user', 'organization']
        indexes = [
            models.Index(fields=['node_type', 'rating']),
        ]

    def __str__(self):
        return f"{self.user.username} rated {self.node_type.name}: {self.rating}/5"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Update node type rating
        self._update_node_type_rating()

    def _update_node_type_rating(self):
        """Update the average rating for the node type"""
        ratings = NodeTypeRating.objects.filter(node_type=self.node_type)
        avg_rating = ratings.aggregate(models.Avg('rating'))['rating__avg'] or 0
        rating_count = ratings.count()

        self.node_type.rating = round(avg_rating, 2)
        self.node_type.rating_count = rating_count
        self.node_type.save(update_fields=['rating', 'rating_count'])


class CustomNodeType(models.Model):
    """Custom node types created by organizations"""

    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('organization', 'Organization'),
        ('public', 'Public'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='custom_nodes')
    base_node_type = models.ForeignKey(NodeType, on_delete=models.CASCADE, related_name='custom_variants')

    # Custom Properties
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255)
    description = models.TextField()

    # Configuration Override
    custom_properties = models.JSONField(default=dict)  # Override base properties
    custom_code = models.TextField(blank=True)  # Custom Python code

    # Sharing
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')
    shared_with_orgs = models.ManyToManyField(Organization, blank=True, related_name='shared_custom_nodes')

    # Versioning
    version = models.CharField(max_length=20, default='1.0.0')
    is_active = models.BooleanField(default=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_custom_nodes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'custom_node_types'
        unique_together = ['organization', 'name']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['visibility', 'is_active']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.organization.name})"


class NodeCredential(models.Model):
    """Stored credentials for node authentication"""

    CREDENTIAL_TYPES = [
        ('api_key', 'API Key'),
        ('oauth2', 'OAuth 2.0'),
        ('basic_auth', 'Basic Authentication'),
        ('bearer_token', 'Bearer Token'),
        ('ssh_key', 'SSH Key'),
        ('database', 'Database Connection'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='credentials')

    # Credential Info
    name = models.CharField(max_length=255)
    credential_type = models.CharField(max_length=50, choices=CREDENTIAL_TYPES)
    service_name = models.CharField(max_length=100)  # e.g., 'slack', 'gmail', 'aws'

    # Encrypted Credential Data
    encrypted_data = models.TextField()  # Encrypted JSON of credential data
    encryption_key_id = models.CharField(max_length=255)  # Key identifier for encryption

    # Metadata
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    # Security
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_credentials')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'node_credentials'
        unique_together = ['organization', 'name']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['service_name', 'credential_type']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.service_name})"

    def get_decrypted_data(self):
        """Decrypt and return credential data"""
        from apps.core.utils import decrypt_data
        return decrypt_data(self.encrypted_data, self.encryption_key_id)

    def set_encrypted_data(self, data):
        """Encrypt and store credential data"""
        from apps.core.utils import encrypt_data
        self.encrypted_data, self.encryption_key_id = encrypt_data(data)

    @property
    def is_expired(self):
        """Check if credential is expired"""
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at


class NodeExecutionLog(models.Model):
    """Detailed logs for individual node executions"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
        ('timeout', 'Timeout'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey('executions.WorkflowExecution', on_delete=models.CASCADE, related_name='node_logs')

    # Node Information
    node_id = models.CharField(max_length=255)  # Node ID from workflow
    node_type = models.ForeignKey(NodeType, on_delete=models.CASCADE, related_name='execution_logs')
    node_name = models.CharField(max_length=255)

    # Execution Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.FloatField(null=True, blank=True)  # milliseconds

    # Data Flow
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)

    # Error Handling
    error_message = models.TextField(blank=True)
    error_type = models.CharField(max_length=100, blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    stack_trace = models.TextField(blank=True)

    # Performance Metrics
    memory_usage_mb = models.FloatField(default=0)
    cpu_usage_percent = models.FloatField(default=0)
    network_requests = models.IntegerField(default=0)

    # Retry Information
    retry_count = models.IntegerField(default=0)
    is_retry = models.BooleanField(default=False)

    class Meta:
        db_table = 'node_execution_logs'
        indexes = [
            models.Index(fields=['execution', 'node_id']),
            models.Index(fields=['node_type', 'status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['status', 'execution_time']),
        ]

    def __str__(self):
        return f"Node {self.node_name} - {self.status}"

    @property
    def duration_ms(self):
        """Get execution duration in milliseconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    def mark_completed(self, output_data=None):
        """Mark node execution as completed"""
        from django.utils import timezone

        self.status = 'completed'
        self.completed_at = timezone.now()
        self.execution_time = self.duration_ms

        if output_data:
            self.output_data = output_data

        self.save()

    def mark_failed(self, error_message, error_type=None, error_details=None, stack_trace=None):
        """Mark node execution as failed"""
        from django.utils import timezone

        self.status = 'failed'
        self.completed_at = timezone.now()
        self.execution_time = self.duration_ms
        self.error_message = error_message

        if error_type:
            self.error_type = error_type
        if error_details:
            self.error_details = error_details
        if stack_trace:
            self.stack_trace = stack_trace

        self.save()


class NodeTypeInstallation(models.Model):
    """Track which node types are installed in which organizations"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='installed_nodes')
    node_type = models.ForeignKey(NodeType, on_delete=models.CASCADE, related_name='installations')

    # Installation details
    installed_version = models.CharField(max_length=20)
    is_enabled = models.BooleanField(default=True)

    # Configuration
    default_config = models.JSONField(default=dict, blank=True)

    # Installation metadata
    installed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='node_installations')
    installed_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'node_type_installations'
        unique_together = ['organization', 'node_type']
        indexes = [
            models.Index(fields=['organization', 'is_enabled']),
            models.Index(fields=['node_type', 'installed_version']),
        ]

    def __str__(self):
        return f"{self.node_type.name} installed in {self.organization.name}"