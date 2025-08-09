from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    """Webhooks application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.webhooks'
    verbose_name = 'Webhooks'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass