"""
Authentication Serializers
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer with additional user data
    """

    def validate(self, attrs):
        data = super().validate(attrs)

        # Add custom claims
        data['user_id'] = self.user.id
        data['username'] = self.user.username
        data['email'] = self.user.email

        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['user_id'] = user.id
        token['username'] = user.username
        token['email'] = user.email

        return token


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    User registration serializer with validation
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    terms_accepted = serializers.BooleanField(write_only=True)
    organization_name = serializers.CharField(max_length=255, required=False)
    invitation_token = serializers.CharField(max_length=255, required=False)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'terms_accepted',
            'organization_name', 'invitation_token'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }

    def validate_email(self, value):
        """Validate email uniqueness"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def validate_username(self, value):
        """Validate username"""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")

        # Additional username validation
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long.")

        if not value.replace('_', '').replace('-', '').isalnum():
            raise serializers.ValidationError("Username can only contain letters, numbers, hyphens, and underscores.")

        return value

    def validate_terms_accepted(self, value):
        """Validate terms acceptance"""
        if not value:
            raise serializers.ValidationError("You must accept the terms and conditions.")
        return value

    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")

        return attrs

    def create(self, validated_data):
        """Create user account"""
        # Remove non-user fields
        validated_data.pop('password_confirm')
        validated_data.pop('terms_accepted')
        validated_data.pop('organization_name', None)
        validated_data.pop('invitation_token', None)

        # Create user
        user = User.objects.create_user(**validated_data)

        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """
    User profile serializer
    """

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'username', 'date_joined', 'last_login', 'full_name']

    def get_full_name(self, obj):
        """Get user's full name"""
        return f"{obj.first_name} {obj.last_name}".strip()

    def validate_email(self, value):
        """Validate email uniqueness for updates"""
        user = self.instance
        if user and User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """
    Password change serializer
    """

    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate_current_password(self, value):
        """Validate current password"""
        user = self.context['user']
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        """Validate new password confirmation"""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords do not match.")

        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """
    Password reset request serializer
    """

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Validate email exists"""
        if not User.objects.filter(email=value).exists():
            # Don't reveal if email exists for security
            # But still validate the format
            pass
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Password reset confirmation serializer
    """

    token = serializers.CharField(required=True)
    password = serializers.CharField(required=True, validators=[validate_password])
    password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")

        return attrs


class OrganizationInvitationSerializer(serializers.Serializer):
    """
    Organization invitation serializer
    """

    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(
        choices=['member', 'admin'],
        default='member',
        required=False
    )
    message = serializers.CharField(max_length=500, required=False)

    def validate_email(self, value):
        """Validate email format"""
        # Additional email validation can be added here
        return value.lower()


class UserBasicSerializer(serializers.ModelSerializer):
    """
    Basic user serializer for nested use
    """

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name']

    def get_full_name(self, obj):
        """Get user's full name"""
        return f"{obj.first_name} {obj.last_name}".strip()


class AuthStatusSerializer(serializers.Serializer):
    """
    Authentication status serializer
    """

    authenticated = serializers.BooleanField()
    user = UserBasicSerializer(required=False)
    organization = serializers.DictField(required=False)


class TokenRefreshSerializer(serializers.Serializer):
    """
    Token refresh serializer
    """

    refresh = serializers.CharField()

    def validate(self, attrs):
        """Validate refresh token"""
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        try:
            refresh = RefreshToken(attrs['refresh'])
            data = {'access': str(refresh.access_token)}

            # Optionally rotate refresh token
            if hasattr(refresh, 'set_jti'):
                refresh.set_jti()
                refresh.set_exp()
                data['refresh'] = str(refresh)

            return data

        except TokenError:
            raise serializers.ValidationError("Invalid or expired refresh token.")


class SocialAuthSerializer(serializers.Serializer):
    """
    Social authentication serializer (for future OAuth integration)
    """

    provider = serializers.ChoiceField(choices=['google', 'github', 'microsoft'])
    access_token = serializers.CharField()

    def validate(self, attrs):
        """Validate social auth token"""
        # This would integrate with social auth providers
        # For now, just return the data
        return attrs


class TwoFactorAuthSerializer(serializers.Serializer):
    """
    Two-factor authentication serializer (for future 2FA implementation)
    """

    token = serializers.CharField(max_length=6, min_length=6)

    def validate_token(self, value):
        """Validate 2FA token"""
        if not value.isdigit():
            raise serializers.ValidationError("Token must be 6 digits.")
        return value


class APIKeySerializer(serializers.Serializer):
    """
    API key generation serializer
    """

    name = serializers.CharField(max_length=255)
    scopes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    expires_at = serializers.DateTimeField(required=False)

    def validate_name(self, value):
        """Validate API key name"""
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Name must be at least 3 characters long.")
        return value.strip()

    def validate_scopes(self, value):
        """Validate API key scopes"""
        valid_scopes = [
            'workflows:read', 'workflows:write', 'workflows:execute',
            'executions:read', 'nodes:read', 'nodes:write',
            'analytics:read', 'organization:read', 'organization:write'
        ]

        for scope in value:
            if scope not in valid_scopes:
                raise serializers.ValidationError(f"Invalid scope: {scope}")

        return value


class SessionSerializer(serializers.Serializer):
    """
    Session information serializer
    """

    session_id = serializers.CharField()
    ip_address = serializers.IPAddressField()
    user_agent = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_activity = serializers.DateTimeField()
    is_current = serializers.BooleanField()


class SecurityEventSerializer(serializers.Serializer):
    """
    Security event logging serializer
    """

    event_type = serializers.ChoiceField(choices=[
        'login_success', 'login_failed', 'logout',
        'password_change', 'password_reset',
        'api_key_created', 'api_key_deleted',
        'suspicious_activity'
    ])
    ip_address = serializers.IPAddressField()
    user_agent = serializers.CharField()
    details = serializers.DictField(required=False)
    timestamp = serializers.DateTimeField()