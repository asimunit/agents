from django.apps import AppConfig


class ExecutionsConfig(AppConfig):
    """Executions application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.executions'
    verbose_name = 'Executions'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass