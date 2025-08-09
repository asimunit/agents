from django.apps import AppConfig


class WorkflowsConfig(AppConfig):
    """Workflows application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workflows'
    verbose_name = 'Workflows'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass