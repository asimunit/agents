"""
Core App Configuration
"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """Application ready hook"""
        # Import signals
        try:
            from . import signals  # noqa
        except ImportError:
            pass

        # Initialize any startup tasks
        self._initialize_default_settings()

    def _initialize_default_settings(self):
        """Initialize default application settings"""
        from django.conf import settings

        # Set default pagination settings if not configured
        if not hasattr(settings, 'REST_FRAMEWORK'):
            settings.REST_FRAMEWORK = {}

        if 'DEFAULT_PAGINATION_CLASS' not in settings.REST_FRAMEWORK:
            settings.REST_FRAMEWORK['DEFAULT_PAGINATION_CLASS'] = 'apps.core.pagination.CustomPageNumberPagination'

        if 'PAGE_SIZE' not in settings.REST_FRAMEWORK:
            settings.REST_FRAMEWORK['PAGE_SIZE'] = 20