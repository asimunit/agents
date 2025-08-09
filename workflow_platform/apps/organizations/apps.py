"""
Organizations App Configuration
"""
from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    """Organizations application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.organizations'
    verbose_name = 'Organizations'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass