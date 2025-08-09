"""
Organization Serializers
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Organization, OrganizationMember, OrganizationInvitation,
    OrganizationUsage, OrganizationAPIKey
)


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for nested serialization"""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name']
        read_only_fields = fields

    def get_full_name(self, obj):
        """Get user's full name"""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class OrganizationSerializer(serializers.ModelSerializer):
    """Organization serializer"""

    created_by = UserBasicSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    workflow_count = serializers.SerializerMethodField()
    usage_limits = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'description', 'plan', 'status',
            'trial_ends_at', 'max_workflows', 'max_executions_per_month',
            'max_users', 'max_api_calls_per_hour', 'settings', 'logo',
            'primary_color', 'created_by', 'created_at', 'updated_at',
            'member_count', 'workflow_count', 'usage_limits'
        ]
        read_only_fields = [
            'id', 'slug', 'created_by', 'created_at', 'updated_at',
            'member_count', 'workflow_count', 'usage_limits'
        ]

    def get_member_count(self, obj):
        """Get number of active members"""
        return obj.members.filter(status='active').count()

    def get_workflow_count(self, obj):
        """Get number of workflows"""
        return obj.workflows.count()

    def get_usage_limits(self, obj):
        """Get usage limits based on plan"""
        return obj.get_usage_limits()


class OrganizationMemberSerializer(serializers.ModelSerializer):
    """Organization member serializer"""

    user = UserBasicSerializer(read_only=True)
    invited_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = OrganizationMember
        fields = [
            'id', 'user', 'role', 'status', 'permissions',
            'invited_by', 'invited_at', 'joined_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'invited_by', 'invited_at', 'joined_at',
            'created_at', 'updated_at'
        ]


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    """Organization invitation serializer"""

    invited_by = UserBasicSerializer(read_only=True)
    organization = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'organization', 'email', 'role', 'status', 'token',
            'invited_by', 'expires_at', 'created_at', 'accepted_at'
        ]
        read_only_fields = [
            'id', 'organization', 'token', 'invited_by', 'expires_at',
            'created_at', 'accepted_at'
        ]


class OrganizationUsageSerializer(serializers.ModelSerializer):
    """Organization usage serializer"""

    class Meta:
        model = OrganizationUsage
        fields = [
            'id', 'workflow_executions', 'api_calls', 'storage_used_mb',
            'bandwidth_used_mb', 'period_start', 'period_end', 'total_cost',
            'created_at'
        ]
        read_only_fields = fields


class OrganizationAPIKeySerializer(serializers.ModelSerializer):
    """Organization API key serializer"""

    created_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = OrganizationAPIKey
        fields = [
            'id', 'name', 'key_preview', 'scopes', 'is_active',
            'expires_at', 'last_used_at', 'created_by', 'created_at'
        ]
        read_only_fields = [
            'id', 'key_preview', 'last_used_at', 'created_by', 'created_at'
        ]

    def create(self, validated_data):
        """Create API key with auto-generated key"""
        api_key = super().create(validated_data)
        # Key is auto-generated in the model's save method
        return api_key


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating organizations"""

    class Meta:
        model = Organization
        fields = ['name', 'description', 'plan']

    def validate_name(self, value):
        """Validate organization name"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Organization name must be at least 2 characters long")
        return value.strip()

    def create(self, validated_data):
        """Create organization with auto-generated slug"""
        import uuid
        from django.utils.text import slugify

        # Generate unique slug
        base_slug = slugify(validated_data['name'])
        slug = base_slug
        counter = 1

        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        validated_data['slug'] = slug

        # Set plan-based limits
        organization = Organization(**validated_data)
        limits = organization.get_usage_limits()
        organization.max_workflows = limits['max_workflows']
        organization.max_executions_per_month = limits['max_executions_per_month']
        organization.max_users = limits['max_users']
        organization.max_api_calls_per_hour = limits['max_api_calls_per_hour']

        organization.save()
        return organization


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

        # Check if user already exists
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists")

        # Check if invitation already exists
        organization = self.context['organization']
        if OrganizationInvitation.objects.filter(
                organization=organization,
                email=value,
                status='pending'
        ).exists():
            raise serializers.ValidationError("Invitation already sent to this email")

        return value


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
            'name', 'description', 'logo', 'primary_color', 'settings'
        ]

    def validate_primary_color(self, value):
        """Validate hex color format"""
        import re
        if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("Invalid hex color format")
        return value

    def validate_settings(self, value):
        """Validate settings JSON"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be a JSON object")

        # Validate specific settings
        allowed_keys = [
            'timezone', 'date_format', 'time_format', 'language',
            'email_notifications', 'slack_webhook', 'custom_domain'
        ]

        for key in value.keys():
            if key not in allowed_keys:
                raise serializers.ValidationError(f"Unknown setting: {key}")

        return value


class OrganizationPlanSerializer(serializers.Serializer):
    """Organization plan upgrade serializer"""

    plan = serializers.ChoiceField(choices=Organization.PLAN_CHOICES)

    def validate_plan(self, value):
        """Validate plan upgrade"""
        organization = self.context['organization']

        # Define plan hierarchy
        plan_hierarchy = ['free', 'pro', 'business', 'enterprise']
        current_index = plan_hierarchy.index(organization.plan)
        new_index = plan_hierarchy.index(value)

        # Only allow upgrades (not downgrades)
        if new_index <= current_index:
            raise serializers.ValidationError("Can only upgrade to a higher plan")

        return value


class OrganizationSummarySerializer(serializers.ModelSerializer):
    """Simplified organization serializer for lists"""

    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'plan', 'status', 'created_at']
        read_only_fields = fields