"""
Analytics App Configuration
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Analytics application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    verbose_name = 'Analytics'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass