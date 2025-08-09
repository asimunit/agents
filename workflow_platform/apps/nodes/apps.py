from django.apps import AppConfig


class NodesConfig(AppConfig):
    """Nodes application configuration"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.nodes'
    verbose_name = 'Nodes'

    def ready(self):
        """Application ready hook"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass

        # Initialize default node types
        self._create_default_node_types()

    def _create_default_node_types(self):
        """Create default node types if they don't exist"""
        try:
            from .models import NodeTypeCategory, NodeType

            # Create default categories if they don't exist
            categories = [
                {'name': 'Data Processing', 'description': 'Nodes for data transformation and processing',
                 'icon': 'database', 'color': '#3b82f6'},
                {'name': 'APIs', 'description': 'API integration nodes', 'icon': 'link', 'color': '#10b981'},
                {'name': 'Logic', 'description': 'Conditional logic and control flow', 'icon': 'branch',
                 'color': '#f59e0b'},
                {'name': 'Utilities', 'description': 'Utility and helper nodes', 'icon': 'tool', 'color': '#6b7280'},
            ]

            for category_data in categories:
                NodeTypeCategory.objects.get_or_create(
                    name=category_data['name'],
                    defaults=category_data
                )
        except Exception:
            pass  # Ignore errors during development