"""
Workflow models - Core workflow management
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator, MaxLengthValidator
from apps.organizations.models import Organization
import uuid
import json


class WorkflowCategory(models.Model):
    """Categories for organizing workflows"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default='#6366f1')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workflow_categories'
        verbose_name_plural = 'Workflow Categories'

    def __str__(self):
        return self.name


class Workflow(models.Model):
    """Main workflow model with advanced features"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
        ('error', 'Error'),
    ]

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('webhook', 'Webhook'),
        ('schedule', 'Schedule'),
        ('event', 'Event'),
        ('api', 'API Call'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='workflows')

    # Basic Info
    name = models.CharField(max_length=255, validators=[MinLengthValidator(2)])
    description = models.TextField(blank=True)
    category = models.ForeignKey(WorkflowCategory, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)

    # Workflow Definition
    nodes = models.JSONField(default=list)  # Node definitions
    connections = models.JSONField(default=list)  # Node connections
    variables = models.JSONField(default=dict)  # Workflow variables

    # Status & Execution
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')

    # Version Control
    version = models.IntegerField(default=1)
    is_latest_version = models.BooleanField(default=True)
    parent_workflow = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='versions')

    # Performance & Optimization
    execution_timeout = models.IntegerField(default=300)  # seconds
    max_retries = models.IntegerField(default=3)
    retry_delay = models.IntegerField(default=60)  # seconds
    parallel_execution = models.BooleanField(default=True)

    # Scheduling (for scheduled workflows)
    schedule_expression = models.CharField(max_length=255, blank=True)  # Cron expression
    schedule_timezone = models.CharField(max_length=50, default='UTC')
    next_run_at = models.DateTimeField(null=True, blank=True)

    # Advanced Features
    settings = models.JSONField(default=dict, blank=True)
    error_handling = models.JSONField(default=dict, blank=True)

    # Permissions & Sharing
    is_public = models.BooleanField(default=False)
    is_template = models.BooleanField(default=False)
    shared_with = models.JSONField(default=list, blank=True)  # User IDs with access

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_workflows')
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='updated_workflows')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Statistics
    total_executions = models.IntegerField(default=0)
    successful_executions = models.IntegerField(default=0)
    failed_executions = models.IntegerField(default=0)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    average_execution_time = models.FloatField(default=0)  # seconds

    class Meta:
        db_table = 'workflows'
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['trigger_type', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['next_run_at']),
            models.Index(fields=['is_template', 'is_public']),
        ]
        unique_together = ['organization', 'name', 'version']

    def __str__(self):
        return f"{self.name} (v{self.version})"

    @property
    def success_rate(self):
        """Calculate workflow success rate"""
        if self.total_executions == 0:
            return 0
        return (self.successful_executions / self.total_executions) * 100

    def create_version(self, created_by):
        """Create a new version of this workflow"""
        # Mark current version as not latest
        Workflow.objects.filter(
            parent_workflow=self.parent_workflow or self,
            is_latest_version=True
        ).update(is_latest_version=False)

        # Create new version
        new_workflow = Workflow.objects.create(
            organization=self.organization,
            name=self.name,
            description=self.description,
            category=self.category,
            nodes=self.nodes,
            connections=self.connections,
            variables=self.variables,
            trigger_type=self.trigger_type,
            execution_timeout=self.execution_timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            parallel_execution=self.parallel_execution,
            schedule_expression=self.schedule_expression,
            schedule_timezone=self.schedule_timezone,
            settings=self.settings,
            error_handling=self.error_handling,
            version=self.version + 1,
            parent_workflow=self.parent_workflow or self,
            is_latest_version=True,
            created_by=created_by,
            updated_by=created_by,
        )

        return new_workflow

    def get_node_count(self):
        """Get total number of nodes in workflow"""
        return len(self.nodes)

    def validate_workflow(self):
        """Validate workflow structure"""
        errors = []

        # Check for at least one trigger node
        trigger_nodes = [node for node in self.nodes if node.get('type', '').startswith('trigger')]
        if not trigger_nodes:
            errors.append("Workflow must have at least one trigger node")

        # Check for circular dependencies
        if self._has_circular_dependency():
            errors.append("Workflow contains circular dependencies")

        # Validate node connections
        connection_errors = self._validate_connections()
        errors.extend(connection_errors)

        return errors

    def _has_circular_dependency(self):
        """Check for circular dependencies in workflow"""
        # Implementation for cycle detection in directed graph
        visited = set()
        rec_stack = set()

        def has_cycle(node_id):
            if node_id in rec_stack:
                return True
            if node_id in visited:
                return False

            visited.add(node_id)
            rec_stack.add(node_id)

            # Get outgoing connections
            outgoing = [conn['target'] for conn in self.connections
                       if conn['source'] == node_id]

            for target in outgoing:
                if has_cycle(target):
                    return True

            rec_stack.remove(node_id)
            return False

        for node in self.nodes:
            if node['id'] not in visited:
                if has_cycle(node['id']):
                    return True

        return False

    def _validate_connections(self):
        """Validate workflow connections"""
        errors = []
        node_ids = {node['id'] for node in self.nodes}

        for connection in self.connections:
            source = connection.get('source')
            target = connection.get('target')

            if source not in node_ids:
                errors.append(f"Invalid connection: source node '{source}' not found")

            if target not in node_ids:
                errors.append(f"Invalid connection: target node '{target}' not found")

        return errors


class WorkflowTemplate(models.Model):
    """Pre-built workflow templates"""

    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.OneToOneField(Workflow, on_delete=models.CASCADE, related_name='template')

    # Template metadata
    title = models.CharField(max_length=255)
    short_description = models.CharField(max_length=500)
    long_description = models.TextField()
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')

    # Categorization
    industry = models.CharField(max_length=100, blank=True)
    use_case = models.CharField(max_length=200, blank=True)

    # Template assets
    thumbnail = models.ImageField(upload_to='template_thumbnails/', null=True, blank=True)
    screenshots = models.JSONField(default=list, blank=True)

    # Usage statistics
    usage_count = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    rating_count = models.IntegerField(default=0)

    # Publishing
    is_featured = models.BooleanField(default=False)
    is_official = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    # Requirements
    required_integrations = models.JSONField(default=list, blank=True)
    required_plan = models.CharField(max_length=20, choices=Organization.PLAN_CHOICES, default='free')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workflow_templates'
        indexes = [
            models.Index(fields=['is_featured', 'published_at']),
            models.Index(fields=['industry', 'use_case']),
            models.Index(fields=['rating', 'usage_count']),
        ]

    def __str__(self):
        return self.title


class WorkflowExecution(models.Model):
    """Workflow execution tracking (overview model)"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('timeout', 'Timeout'),
    ]

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('webhook', 'Webhook'),
        ('schedule', 'Schedule'),
        ('api', 'API'),
        ('retry', 'Retry'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='executions')

    # Execution details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger_source = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.FloatField(null=True, blank=True)  # seconds

    # Execution context
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)

    # Performance metrics
    nodes_executed = models.IntegerField(default=0)
    nodes_failed = models.IntegerField(default=0)
    memory_usage_mb = models.FloatField(default=0)
    cpu_usage_percent = models.FloatField(default=0)

    # Retry information
    retry_count = models.IntegerField(default=0)
    parent_execution = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)

    # Additional metadata
    execution_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'workflow_executions'
        indexes = [
            models.Index(fields=['workflow', 'status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['trigger_source', 'status']),
            models.Index(fields=['triggered_by', 'started_at']),
        ]

    def __str__(self):
        return f"Execution {self.id} - {self.workflow.name} ({self.status})"

    @property
    def duration(self):
        """Get execution duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def mark_completed(self, output_data=None):
        """Mark execution as completed"""
        from django.utils import timezone

        self.status = 'completed'
        self.completed_at = timezone.now()
        self.execution_time = self.duration

        if output_data:
            self.output_data = output_data

        self.save()

        # Update workflow statistics
        self.workflow.total_executions += 1
        self.workflow.successful_executions += 1
        self.workflow.last_executed_at = self.completed_at

        # Update average execution time
        if self.workflow.average_execution_time == 0:
            self.workflow.average_execution_time = self.execution_time
        else:
            total_time = (self.workflow.average_execution_time *
                         (self.workflow.successful_executions - 1) + self.execution_time)
            self.workflow.average_execution_time = total_time / self.workflow.successful_executions

        self.workflow.save()

    def mark_failed(self, error_message, error_details=None):
        """Mark execution as failed"""
        from django.utils import timezone

        self.status = 'failed'
        self.completed_at = timezone.now()
        self.execution_time = self.duration
        self.error_message = error_message

        if error_details:
            self.error_details = error_details

        self.save()

        # Update workflow statistics
        self.workflow.total_executions += 1
        self.workflow.failed_executions += 1
        self.workflow.save()


class WorkflowShare(models.Model):
    """Workflow sharing permissions"""

    PERMISSION_CHOICES = [
        ('view', 'View Only'),
        ('edit', 'Edit'),
        ('execute', 'Execute'),
        ('admin', 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='shares')
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_workflows')
    permission = models.CharField(max_length=20, choices=PERMISSION_CHOICES, default='view')

    shared_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflow_shares_given')
    shared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workflow_shares'
        unique_together = ['workflow', 'shared_with']

    def __str__(self):
        return f"{self.workflow.name} shared with {self.shared_with.username}"


class WorkflowComment(models.Model):
    """Comments on workflows for collaboration"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflow_comments')

    content = models.TextField()
    node_id = models.CharField(max_length=255, blank=True)  # Comment on specific node

    # Threading
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workflow_comments'
        indexes = [
            models.Index(fields=['workflow', 'created_at']),
            models.Index(fields=['node_id']),
        ]

    def __str__(self):
        return f"Comment by {self.author.username} on {self.workflow.name}"