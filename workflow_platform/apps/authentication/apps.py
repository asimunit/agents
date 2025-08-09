"""
Authentication App Configuration
"""
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """Authentication application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = 'Authentication'

    def ready(self):
        """Application ready hook"""
        # Import signals
        try:
            from . import signals  # noqa
        except ImportError:
            pass