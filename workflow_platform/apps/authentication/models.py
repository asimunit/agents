"""
Authentication Models - Extended user functionality
"""
from django.db import models
from django.contrib.auth.models import User
import django.utils.timezone as dj_timezone
import uuid


class UserProfile(models.Model):
    """Extended user profile"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Profile information
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    # Profile picture
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # Preferences
    timezone = models.CharField(max_length=50, default='UTC')
    language = models.CharField(max_length=10, default='en')

    # Notifications preferences
    email_notifications = models.BooleanField(default=True)
    workflow_notifications = models.BooleanField(default=True)
    execution_notifications = models.BooleanField(default=True)

    # Two-factor authentication
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_backup_codes = models.JSONField(default=list, blank=True)

    # API access
    api_access_enabled = models.BooleanField(default=True)
    api_rate_limit = models.IntegerField(default=1000)  # requests per hour

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(default=dj_timezone.now)

    class Meta:
        db_table = 'user_profiles'

    def __str__(self):
        return f"{self.user.username} Profile"

    @property
    def full_name(self):
        """Get user's full name"""
        return f"{self.user.first_name} {self.user.last_name}".strip()

    def update_last_activity(self):
        """Update last activity timestamp"""
        self.last_activity = dj_timezone.now()
        self.save(update_fields=['last_activity'])


class LoginAttempt(models.Model):
    """Track login attempts for security"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()

    success = models.BooleanField()
    failure_reason = models.CharField(max_length=100, blank=True)

    # Geolocation (if available)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_attempts'
        indexes = [
            models.Index(fields=['email', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['success', 'created_at']),
        ]

    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{status} login for {self.email} from {self.ip_address}"


class APIToken(models.Model):
    """Personal API tokens for users"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')

    name = models.CharField(max_length=100)
    token = models.CharField(max_length=255, unique=True)

    # Permissions
    scopes = models.JSONField(default=list)  # ['workflows:read', 'workflows:write', etc.]

    # Usage tracking
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)

    # Status
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.user.username}"

    @property
    def is_expired(self):
        """Check if token is expired"""
        if self.expires_at:
            return dj_timezone.now() > self.expires_at
        return False

    def update_usage(self):
        """Update token usage statistics"""
        self.last_used_at = dj_timezone.now()
        self.usage_count += 1
        self.save(update_fields=['last_used_at', 'usage_count'])


class PasswordResetToken(models.Model):
    """Password reset tokens"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user', 'used']),
        ]

    def __str__(self):
        return f"Password reset token for {self.user.username}"

    @property
    def is_expired(self):
        """Check if token is expired"""
        return dj_timezone.now() > self.expires_at

    @property
    def is_valid(self):
        """Check if token is valid"""
        return not self.used and not self.is_expired


# Signal to create user profile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()