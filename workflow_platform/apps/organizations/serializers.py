"""
Organizations Serializers - API serialization for organization management
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import secrets
from .models import (
    Organization, OrganizationMember, OrganizationInvitation,
    OrganizationAPIKey, OrganizationUsage
)


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for nested serialization"""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'full_name']
        read_only_fields = fields

    def get_full_name(self, obj):
        """Get user's full name"""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class OrganizationSerializer(serializers.ModelSerializer):
    """Organization serializer"""

    created_by = UserBasicSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    workflow_count = serializers.SerializerMethodField()
    current_user_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'description', 'logo', 'website',
            'plan', 'status', 'primary_color', 'settings',
            'max_workflows', 'max_executions_per_month', 'max_users',
            'max_api_calls_per_hour', 'member_count', 'workflow_count',
            'current_user_role', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'member_count', 'workflow_count', 'current_user_role',
            'created_by', 'created_at', 'updated_at'
        ]

    def get_member_count(self, obj):
        """Get number of active members"""
        return obj.members.filter(status='active').count()

    def get_workflow_count(self, obj):
        """Get number of workflows"""
        return obj.workflows.filter(is_latest_version=True).count()

    def get_current_user_role(self, obj):
        """Get current user's role in organization"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                member = obj.members.get(user=request.user, status='active')
                return member.role
            except OrganizationMember.DoesNotExist:
                pass
        return None


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating organizations"""

    class Meta:
        model = Organization
        fields = ['name', 'description', 'logo', 'website', 'primary_color']

    def validate_name(self, value):
        """Validate organization name"""
        if Organization.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Organization with this name already exists")
        return value

    def create(self, validated_data):
        """Create organization with owner membership"""
        request = self.context['request']

        # Generate unique slug
        import re
        base_slug = re.sub(r'[^a-zA-Z0-9\-]', '', validated_data['name'].lower().replace(' ', '-'))
        slug = base_slug
        counter = 1

        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Set plan limits based on default plan
        plan_limits = self._get_plan_limits('free')

        organization = Organization.objects.create(
            slug=slug,
            created_by=request.user,
            plan='free',
            **validated_data,
            **plan_limits
        )

        # Create owner membership
        OrganizationMember.objects.create(
            organization=organization,
            user=request.user,
            role='owner',
            status='active',
            joined_at=timezone.now()
        )

        return organization

    def _get_plan_limits(self, plan):
        """Get limits for organization plan"""
        plan_limits = {
            'free': {
                'max_workflows': 5,
                'max_executions_per_month': 1000,
                'max_users': 3,
                'max_api_calls_per_hour': 100,
            },
            'pro': {
                'max_workflows': 50,
                'max_executions_per_month': 10000,
                'max_users': 10,
                'max_api_calls_per_hour': 1000,
            },
            'enterprise': {
                'max_workflows': -1,  # Unlimited
                'max_executions_per_month': -1,
                'max_users': -1,
                'max_api_calls_per_hour': -1,
            }
        }

        return plan_limits.get(plan, plan_limits['free'])


class OrganizationMemberSerializer(serializers.ModelSerializer):
    """Organization member serializer"""

    user = UserBasicSerializer(read_only=True)
    invited_by = UserBasicSerializer(read_only=True)
    organization = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OrganizationMember
        fields = [
            'id', 'organization', 'user', 'role', 'status', 'permissions',
            'invited_by', 'invited_at', 'joined_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'organization', 'user', 'invited_by', 'invited_at',
            'joined_at', 'created_at', 'updated_at'
        ]


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    """Organization invitation serializer"""

    organization = serializers.StringRelatedField(read_only=True)
    invited_by = UserBasicSerializer(read_only=True)
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'organization', 'email', 'role', 'status', 'token',
            'invited_by', 'expires_at', 'is_expired', 'created_at', 'accepted_at'
        ]
        read_only_fields = [
            'id', 'organization', 'token', 'invited_by', 'is_expired',
            'created_at', 'accepted_at'
        ]


class OrganizationInviteSerializer(serializers.Serializer):
    """Serializer for sending organization invitations"""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMember.ROLE_CHOICES,
        default='member'
    )
    message = serializers.CharField(max_length=500, required=False)

    def validate_email(self, value):
        """Validate email format and uniqueness"""
        value = value.lower().strip()

        # Check if user already exists in organization
        organization = self.context['organization']
        if OrganizationMember.objects.filter(
                organization=organization,
                user__email=value,
                status='active'
        ).exists():
            raise serializers.ValidationError("User is already a member of this organization")

        # Check if invitation already exists
        if OrganizationInvitation.objects.filter(
                organization=organization,
                email=value,
                status='pending'
        ).exists():
            raise serializers.ValidationError("Invitation already sent to this email")

        return value


class OrganizationAPIKeySerializer(serializers.ModelSerializer):
    """Organization API key serializer"""

    organization = serializers.StringRelatedField(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    key_preview = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationAPIKey
        fields = [
            'id', 'name', 'description', 'organization', 'key_preview',
            'scopes', 'rate_limit_requests', 'allowed_ips', 'is_active',
            'expires_at', 'is_expired', 'usage_count', 'last_used_at',
            'created_by', 'created_at'
        ]
        read_only_fields = [
            'id', 'organization', 'key_preview', 'is_expired', 'usage_count',
            'last_used_at', 'created_by', 'created_at'
        ]

    def get_key_preview(self, obj):
        """Get masked API key for display"""
        if obj.key:
            return f"{obj.key[:8]}...{obj.key[-4:]}"
        return None

    def get_is_expired(self, obj):
        """Check if API key is expired"""
        if obj.expires_at:
            return timezone.now() > obj.expires_at
        return False


class OrganizationAPIKeyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating API keys"""

    class Meta:
        model = OrganizationAPIKey
        fields = [
            'name', 'description', 'scopes', 'rate_limit_requests',
            'allowed_ips', 'expires_at'
        ]

    def validate_scopes(self, value):
        """Validate API key scopes"""
        if not value:
            return ['read']  # Default scope

        valid_scopes = ['read', 'write', 'delete', 'execute', 'admin']
        for scope in value:
            if scope not in valid_scopes:
                raise serializers.ValidationError(f"Invalid scope: {scope}")

        return value

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
        """Create API key with generated key"""
        # Generate secure API key
        key = f"wfp_{secrets.token_urlsafe(32)}"

        api_key = OrganizationAPIKey.objects.create(
            key=key,
            **validated_data
        )

        return api_key


class OrganizationUsageSerializer(serializers.ModelSerializer):
    """Organization usage serializer"""

    organization = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OrganizationUsage
        fields = [
            'id', 'organization', 'date', 'workflow_count', 'execution_count',
            'user_count', 'api_calls_count', 'storage_used_mb', 'usage_breakdown',
            'created_at'
        ]
        read_only_fields = fields


class OrganizationStatsSerializer(serializers.Serializer):
    """Organization statistics serializer"""

    users = serializers.IntegerField()
    workflows = serializers.IntegerField()
    active_workflows = serializers.IntegerField()
    total_executions = serializers.IntegerField()
    recent_activity = serializers.DictField()
    plan_usage = serializers.DictField()


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    """Organization settings serializer"""

    class Meta:
        model = Organization
        fields = [
            'name', 'description', 'logo', 'website', 'primary_color', 'settings'
        ]

    def validate_settings(self, value):
        """Validate settings structure"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be a JSON object")

        # Validate specific settings
        allowed_settings = [
            'notifications', 'security', 'integrations', 'branding',
            'workflow_defaults', 'execution_defaults'
        ]

        for key in value.keys():
            if key not in allowed_settings:
                raise serializers.ValidationError(f"Invalid setting: {key}")

        return value


class OrganizationUsageSummarySerializer(serializers.Serializer):
    """Organization usage summary serializer"""

    current_usage = serializers.DictField()
    historical_usage = OrganizationUsageSerializer(many=True)
    period_days = serializers.IntegerField()


class OrganizationPlanUpgradeSerializer(serializers.Serializer):
    """Serializer for plan upgrades"""

    new_plan = serializers.ChoiceField(
        choices=[('free', 'Free'), ('pro', 'Pro'), ('enterprise', 'Enterprise')]
    )
    billing_info = serializers.DictField(required=False)

    def validate_new_plan(self, value):
        """Validate plan upgrade"""
        organization = self.context['organization']

        # Define plan hierarchy
        plan_hierarchy = {'free': 0, 'pro': 1, 'enterprise': 2}

        current_level = plan_hierarchy.get(organization.plan, 0)
        new_level = plan_hierarchy.get(value, 0)

        if new_level < current_level:
            raise serializers.ValidationError("Cannot downgrade plan through this endpoint")

        if new_level == current_level:
            raise serializers.ValidationError("Organization is already on this plan")

        return value

    def update_organization_plan(self, organization):
        """Update organization plan and limits"""
        new_plan = self.validated_data['new_plan']

        # Get new plan limits
        plan_limits = {
            'free': {
                'max_workflows': 5,
                'max_executions_per_month': 1000,
                'max_users': 3,
                'max_api_calls_per_hour': 100,
            },
            'pro': {
                'max_workflows': 50,
                'max_executions_per_month': 10000,
                'max_users': 10,
                'max_api_calls_per_hour': 1000,
            },
            'enterprise': {
                'max_workflows': -1,
                'max_executions_per_month': -1,
                'max_users': -1,
                'max_api_calls_per_hour': -1,
            }
        }

        limits = plan_limits.get(new_plan, plan_limits['free'])

        # Update organization
        organization.plan = new_plan
        organization.max_workflows = limits['max_workflows']
        organization.max_executions_per_month = limits['max_executions_per_month']
        organization.max_users = limits['max_users']
        organization.max_api_calls_per_hour = limits['max_api_calls_per_hour']
        organization.save()

        return organization


class OrganizationMemberRoleChangeSerializer(serializers.Serializer):
    """Serializer for changing member roles"""

    role = serializers.ChoiceField(choices=OrganizationMember.ROLE_CHOICES)

    def validate_role(self, value):
        """Validate role change"""
        member = self.context['member']
        request = self.context['request']

        # Get requesting user's membership
        requesting_member = request.user.organization_memberships.filter(
            organization=member.organization
        ).first()

        if not requesting_member:
            raise serializers.ValidationError("You are not a member of this organization")

        # Only owners can assign owner role
        if value == 'owner' and requesting_member.role != 'owner':
            raise serializers.ValidationError("Only owners can assign owner role")

        # Only owners and admins can change roles
        if requesting_member.role not in ['owner', 'admin']:
            raise serializers.ValidationError("Permission denied")

        return value


class BulkInviteSerializer(serializers.Serializer):
    """Serializer for bulk invitations"""

    invitations = serializers.ListField(
        child=serializers.DictField(),
        max_length=50  # Limit bulk invitations
    )

    def validate_invitations(self, value):
        """Validate bulk invitation data"""
        validated_invitations = []

        for i, invitation_data in enumerate(value):
            # Validate each invitation
            email = invitation_data.get('email')
            role = invitation_data.get('role', 'member')

            if not email:
                raise serializers.ValidationError(f"Invitation {i+1}: Email is required")

            if role not in dict(OrganizationMember.ROLE_CHOICES):
                raise serializers.ValidationError(f"Invitation {i+1}: Invalid role")

            # Check email format
            try:
                serializers.EmailField().run_validation(email)
            except serializers.ValidationError:
                raise serializers.ValidationError(f"Invitation {i+1}: Invalid email format")

            validated_invitations.append({
                'email': email.lower().strip(),
                'role': role,
                'message': invitation_data.get('message', '')
            })

        return validated_invitations