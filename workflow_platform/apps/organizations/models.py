"""
Organization models for multi-tenant architecture
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator
import uuid


class Organization(models.Model):
    """Organization model for multi-tenancy"""

    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('business', 'Business'),
        ('enterprise', 'Enterprise'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('trial', 'Trial'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, validators=[MinLengthValidator(2)])
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Subscription & Billing
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_id = models.CharField(max_length=255, blank=True)

    # Limits based on plan
    max_workflows = models.IntegerField(default=5)
    max_executions_per_month = models.IntegerField(default=1000)
    max_users = models.IntegerField(default=1)
    max_api_calls_per_hour = models.IntegerField(default=100)

    # Organization settings
    settings = models.JSONField(default=dict, blank=True)

    # Branding (for white-label)
    logo = models.ImageField(upload_to='org_logos/', null=True, blank=True)
    primary_color = models.CharField(max_length=7, default='#6366f1')  # Hex color

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_organizations')

    class Meta:
        db_table = 'organizations'
        indexes = [
            models.Index(fields=['plan', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_trial_expired(self):
        if not self.trial_ends_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.trial_ends_at

    def get_usage_limits(self):
        """Get current usage limits based on plan"""
        limits = {
            'free': {
                'max_workflows': 5,
                'max_executions_per_month': 1000,
                'max_users': 1,
                'max_api_calls_per_hour': 100,
            },
            'pro': {
                'max_workflows': 50,
                'max_executions_per_month': 50000,
                'max_users': 5,
                'max_api_calls_per_hour': 1000,
            },
            'business': {
                'max_workflows': 500,
                'max_executions_per_month': 500000,
                'max_users': 25,
                'max_api_calls_per_hour': 5000,
            },
            'enterprise': {
                'max_workflows': -1,  # Unlimited
                'max_executions_per_month': -1,
                'max_users': -1,
                'max_api_calls_per_hour': -1,
            }
        }
        return limits.get(self.plan, limits['free'])


class OrganizationMember(models.Model):
    """Organization membership with roles"""

    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('invited', 'Invited'),
        ('inactive', 'Inactive'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited')

    # Permissions
    permissions = models.JSONField(default=dict, blank=True)

    # Invitation
    invitation_token = models.CharField(max_length=255, blank=True)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_invitations')
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organization_members'
        unique_together = ['organization', 'user']
        indexes = [
            models.Index(fields=['role', 'status']),
            models.Index(fields=['organization', 'status']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.role})"

    def has_permission(self, permission):
        """Check if member has specific permission"""
        role_permissions = {
            'owner': ['*'],  # All permissions
            'admin': [
                'workflow.create', 'workflow.edit', 'workflow.delete', 'workflow.execute',
                'user.invite', 'user.manage', 'org.settings',
            ],
            'member': [
                'workflow.create', 'workflow.edit', 'workflow.execute',
            ],
            'viewer': [
                'workflow.view',
            ],
        }

        permissions = role_permissions.get(self.role, [])
        if '*' in permissions:
            return True

        # Check custom permissions
        custom_permissions = self.permissions.get('permissions', [])
        return permission in permissions or permission in custom_permissions


class OrganizationInvitation(models.Model):
    """Track organization invitations"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=OrganizationMember.ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    token = models.CharField(max_length=255, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_org_invitations')

    # Expiration
    expires_at = models.DateTimeField()

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'organization_invitations'
        unique_together = ['organization', 'email']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"Invitation to {self.email} for {self.organization.name}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at


class OrganizationUsage(models.Model):
    """Track organization usage for billing and limits"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='usage_records')

    # Usage metrics
    workflow_executions = models.IntegerField(default=0)
    api_calls = models.IntegerField(default=0)
    storage_used_mb = models.FloatField(default=0)
    bandwidth_used_mb = models.FloatField(default=0)

    # Time period
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Billing
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'organization_usage'
        unique_together = ['organization', 'period_start']
        indexes = [
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['organization', 'period_start']),
        ]

    def __str__(self):
        return f"Usage for {self.organization.name} ({self.period_start} - {self.period_end})"


class OrganizationAPIKey(models.Model):
    """API keys for organization-level access"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='api_keys')

    name = models.CharField(max_length=255)
    key = models.CharField(max_length=255, unique=True)
    key_preview = models.CharField(max_length=20)  # First few chars for display

    # Permissions
    scopes = models.JSONField(default=list)  # ['workflows:read', 'workflows:write', etc.]

    # Status
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    # Security
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_api_keys')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'organization_api_keys'
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['organization', 'is_active']),
        ]

    def __str__(self):
        return f"API Key: {self.name} ({self.organization.name})"

    def save(self, *args, **kwargs):
        if not self.key:
            import secrets
            self.key = f"wp_{secrets.token_urlsafe(32)}"
            self.key_preview = self.key[:8] + "..."
        super().save(*args, **kwargs)