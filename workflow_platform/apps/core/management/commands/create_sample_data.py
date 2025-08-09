"""
Safe Django Management Command for Sample Data Generation
This version handles missing models gracefully and provides better error reporting
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from faker import Faker
import random
import uuid
import json
import importlib

fake = Faker()

class Command(BaseCommand):
    help = 'Generate sample data for testing the workflow platform (safe version)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=20,
            help='Number of users to create (default: 20)',
        )
        parser.add_argument(
            '--organizations',
            type=int,
            default=5,
            help='Number of organizations to create (default: 5)',
        )
        parser.add_argument(
            '--workflows',
            type=int,
            default=50,
            help='Number of workflows to create (default: 50)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before creating new data',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting safe sample data generation...')
        )

        # Try to import models and track what's available
        self.available_models = self.check_available_models()

        if not self.available_models:
            self.stdout.write(
                self.style.ERROR('❌ No models could be imported. Check your Django setup.')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f'✅ Found {len(self.available_models)} available model groups')
        )

        if options['clear']:
            self.clear_existing_data()

        # Store created objects for relationships
        self.users = []
        self.organizations = []
        self.workflows = []
        self.node_types = []
        self.categories = []
        self.node_categories = []

        # Create data in order of dependencies
        self.create_users(options['users'])

        if 'organizations' in self.available_models:
            self.create_organizations(options['organizations'])

        if 'workflows' in self.available_models:
            self.create_workflow_categories()
            self.create_workflows(options['workflows'])

        if 'nodes' in self.available_models:
            self.create_node_type_categories()
            self.create_node_types(25)

        if 'executions' in self.available_models and self.workflows:
            self.create_executions(50)

        if 'analytics' in self.available_models and self.organizations:
            self.create_analytics_dashboards(5)

        # Final summary
        self.print_summary()

    def check_available_models(self):
        """Check which model groups are available for import"""
        available = {}

        # Check organizations models
        try:
            from apps.organizations.models import Organization, OrganizationMember
            available['organizations'] = {
                'Organization': Organization,
                'OrganizationMember': OrganizationMember
            }
            self.stdout.write('✅ Organizations models imported')
        except ImportError as e:
            self.stdout.write(f'⚠️  Organizations models not available: {e}')

        # Check workflows models
        try:
            from apps.workflows.models import Workflow, WorkflowCategory
            available['workflows'] = {
                'Workflow': Workflow,
                'WorkflowCategory': WorkflowCategory
            }
            self.stdout.write('✅ Workflows models imported')

            # Try to import WorkflowExecution
            try:
                from apps.workflows.models import WorkflowExecution
                available['workflows']['WorkflowExecution'] = WorkflowExecution
            except ImportError:
                self.stdout.write('⚠️  WorkflowExecution not available')

        except ImportError as e:
            self.stdout.write(f'⚠️  Workflows models not available: {e}')

        # Check nodes models
        try:
            from apps.nodes.models import NodeType, NodeCategory
            available['nodes'] = {
                'NodeType': NodeType,
                'NodeCategory': NodeCategory
            }
            self.stdout.write('✅ Nodes models imported')

            # Try to import NodeCredential
            try:
                from apps.nodes.models import NodeCredential
                available['nodes']['NodeCredential'] = NodeCredential
            except ImportError:
                self.stdout.write('⚠️  NodeCredential not available')

        except ImportError as e:
            self.stdout.write(f'⚠️  Nodes models not available: {e}')

        # Check executions models
        try:
            from apps.executions.models import ExecutionQueue, ExecutionHistory
            available['executions'] = {
                'ExecutionQueue': ExecutionQueue,
                'ExecutionHistory': ExecutionHistory
            }
            self.stdout.write('✅ Executions models imported')

            # Try to import ExecutionSchedule
            try:
                from apps.executions.models import ExecutionSchedule
                available['executions']['ExecutionSchedule'] = ExecutionSchedule
            except ImportError:
                self.stdout.write('⚠️  ExecutionSchedule not available')

        except ImportError as e:
            self.stdout.write(f'⚠️  Executions models not available: {e}')

        # Check analytics models
        try:
            from apps.analytics.models import AnalyticsDashboard, AnalyticsWidget
            available['analytics'] = {
                'AnalyticsDashboard': AnalyticsDashboard,
                'AnalyticsWidget': AnalyticsWidget
            }
            self.stdout.write('✅ Analytics models imported')
        except ImportError as e:
            self.stdout.write(f'⚠️  Analytics models not available: {e}')

        return available

    def clear_existing_data(self):
        """Clear existing test data safely"""
        self.stdout.write('🧹 Clearing existing data...')

        try:
            if 'analytics' in self.available_models:
                self.available_models['analytics']['AnalyticsWidget'].objects.all().delete()
                self.available_models['analytics']['AnalyticsDashboard'].objects.all().delete()

            if 'executions' in self.available_models:
                for model_name in ['ExecutionSchedule', 'ExecutionHistory', 'ExecutionQueue']:
                    if model_name in self.available_models['executions']:
                        self.available_models['executions'][model_name].objects.all().delete()

            if 'nodes' in self.available_models:
                for model_name in ['NodeCredential']:
                    if model_name in self.available_models['nodes']:
                        self.available_models['nodes'][model_name].objects.all().delete()
                self.available_models['nodes']['NodeType'].objects.all().delete()
                self.available_models['nodes']['NodeCategory'].objects.all().delete()

            if 'workflows' in self.available_models:
                if 'WorkflowExecution' in self.available_models['workflows']:
                    self.available_models['workflows']['WorkflowExecution'].objects.all().delete()
                self.available_models['workflows']['Workflow'].objects.all().delete()
                self.available_models['workflows']['WorkflowCategory'].objects.all().delete()

            if 'organizations' in self.available_models:
                self.available_models['organizations']['OrganizationMember'].objects.all().delete()
                self.available_models['organizations']['Organization'].objects.all().delete()

            User.objects.filter(is_superuser=False).delete()  # Keep superusers

            self.stdout.write(self.style.SUCCESS('✅ Existing data cleared'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Error clearing data: {e}'))

    def create_users(self, count):
        """Create sample users"""
        self.stdout.write(f'👤 Creating {count} users...')

        for i in range(count):
            user = User.objects.create_user(
                username=fake.user_name(),
                email=fake.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                password='testpass123'
            )
            self.users.append(user)

        # Create admin user if it doesn't exist
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()

        self.users.append(admin_user)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(self.users)} users'))

    def create_organizations(self, count):
        """Create sample organizations"""
        if 'organizations' not in self.available_models:
            self.stdout.write(self.style.WARNING('⚠️  Skipping organizations - models not available'))
            return

        self.stdout.write(f'🏢 Creating {count} organizations...')

        Organization = self.available_models['organizations']['Organization']
        OrganizationMember = self.available_models['organizations']['OrganizationMember']

        org_names = [
            'TechCorp Solutions', 'DataFlow Industries', 'AutoMate Systems',
            'CloudWorks Inc', 'ProcessPro Ltd', 'FlowTech Dynamics'
        ]

        for i in range(count):
            try:
                org = Organization.objects.create(
                    name=org_names[i] if i < len(org_names) else fake.company(),
                    slug=fake.slug(),
                    description=fake.text(max_nb_chars=200),
                    plan=random.choice(['free', 'pro', 'enterprise']),
                    created_by=random.choice(self.users)
                )
                self.organizations.append(org)

                # Add members to organization
                members = random.sample(self.users, k=min(random.randint(2, 6), len(self.users)))
                for j, user in enumerate(members):
                    role = 'owner' if j == 0 else random.choice(['admin', 'member'])
                    OrganizationMember.objects.create(
                        organization=org,
                        user=user,
                        role=role,
                        status='active',
                        joined_at=timezone.now()
                    )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating organization: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(self.organizations)} organizations'))

    def create_workflow_categories(self):
        """Create workflow categories"""
        if 'workflows' not in self.available_models:
            return

        self.stdout.write('📁 Creating workflow categories...')

        WorkflowCategory = self.available_models['workflows']['WorkflowCategory']

        categories_data = [
            {'name': 'Data Processing', 'description': 'ETL and data transformation workflows', 'icon': 'database', 'color': '#3B82F6'},
            {'name': 'Automation', 'description': 'Business process automation', 'icon': 'cog', 'color': '#10B981'},
            {'name': 'Integration', 'description': 'API and system integrations', 'icon': 'link', 'color': '#F59E0B'},
            {'name': 'Notifications', 'description': 'Alert and notification workflows', 'icon': 'bell', 'color': '#EF4444'},
            {'name': 'Analytics', 'description': 'Data analysis and reporting', 'icon': 'chart-bar', 'color': '#8B5CF6'},
            {'name': 'Security', 'description': 'Security and compliance workflows', 'icon': 'shield', 'color': '#6B7280'}
        ]

        for cat_data in categories_data:
            try:
                category = WorkflowCategory.objects.create(**cat_data)
                self.categories.append(category)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating category: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(self.categories)} workflow categories'))

    def create_node_type_categories(self):
        """Create node type categories"""
        if 'nodes' not in self.available_models:
            return

        self.stdout.write('🧩 Creating node type categories...')

        NodeCategory = self.available_models['nodes']['NodeCategory']

        node_categories = [
            {'name': 'Triggers', 'display_name': 'Triggers', 'description': 'Workflow trigger nodes', 'icon': 'play', 'color': '#10B981'},
            {'name': 'Actions', 'display_name': 'Actions', 'description': 'Action execution nodes', 'icon': 'lightning', 'color': '#3B82F6'},
            {'name': 'Logic', 'display_name': 'Logic', 'description': 'Logic and control flow nodes', 'icon': 'branch', 'color': '#F59E0B'},
            {'name': 'Data', 'display_name': 'Data', 'description': 'Data manipulation nodes', 'icon': 'database', 'color': '#8B5CF6'},
            {'name': 'Communication', 'display_name': 'Communication', 'description': 'Communication and messaging', 'icon': 'mail', 'color': '#EF4444'},
            {'name': 'Utilities', 'display_name': 'Utilities', 'description': 'Utility and helper nodes', 'icon': 'tools', 'color': '#6B7280'}
        ]

        created_categories = []
        for cat_data in node_categories:
            try:
                category, created = NodeCategory.objects.get_or_create(
                    name=cat_data['name'],
                    defaults=cat_data
                )
                created_categories.append(category)
                if created:
                    self.stdout.write(f'✅ Created category: {category.name}')
                else:
                    self.stdout.write(f'ℹ️  Category already exists: {category.name}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating node category: {e}'))

        self.node_categories = created_categories
        self.stdout.write(self.style.SUCCESS('✅ Created node type categories'))

    def create_node_types(self, count):
        """Create sample node types"""
        if 'nodes' not in self.available_models or not self.node_categories:
            self.stdout.write(self.style.WARNING('⚠️  Skipping node types - missing dependencies'))
            return

        self.stdout.write(f'⚙️ Creating {count} node types...')

        NodeType = self.available_models['nodes']['NodeType']

        # Map category names to objects
        category_map = {cat.name: cat for cat in self.node_categories}

        node_templates = [
            {'name': 'webhook_trigger', 'display_name': 'Webhook Trigger', 'category_name': 'Triggers', 'node_type': 'trigger'},
            {'name': 'schedule_trigger', 'display_name': 'Schedule Trigger', 'category_name': 'Triggers', 'node_type': 'trigger'},
            {'name': 'http_request', 'display_name': 'HTTP Request', 'category_name': 'Actions', 'node_type': 'action'},
            {'name': 'send_email', 'display_name': 'Send Email', 'category_name': 'Actions', 'node_type': 'action'},
            {'name': 'if_condition', 'display_name': 'If Condition', 'category_name': 'Logic', 'node_type': 'condition'},
            {'name': 'json_parser', 'display_name': 'JSON Parser', 'category_name': 'Data', 'node_type': 'transform'},
        ]

        for template in node_templates:
            try:
                category = category_map.get(template['category_name'])
                if not category:
                    self.stdout.write(f'⚠️  Category not found: {template["category_name"]}')
                    continue

                node_type = NodeType.objects.create(
                    name=template['name'],
                    display_name=template['display_name'],
                    description=fake.text(max_nb_chars=150),
                    category=category,
                    node_type=template['node_type'],
                    source='built_in',
                    executor_class=f'apps.nodes.executors.{template["name"]}.{template["name"].title()}Executor',
                    properties_schema={
                        'type': 'object',
                        'properties': {
                            'config': {'type': 'object'},
                            'timeout': {'type': 'integer', 'default': 30}
                        }
                    },
                    inputs_schema=[
                        {'name': 'input', 'type': 'any', 'required': True}
                    ],
                    outputs_schema=[
                        {'name': 'output', 'type': 'any'}
                    ],
                    usage_count=random.randint(0, 1000),
                    rating=round(random.uniform(3.0, 5.0), 1)
                )
                self.node_types.append(node_type)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating node type: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(self.node_types)} node types'))

    def create_workflows(self, count):
        """Create sample workflows"""
        if 'workflows' not in self.available_models or not self.organizations:
            self.stdout.write(self.style.WARNING('⚠️  Skipping workflows - missing dependencies'))
            return

        self.stdout.write(f'🔄 Creating {count} workflows...')

        Workflow = self.available_models['workflows']['Workflow']

        for i in range(count):
            try:
                workflow_name = f"Sample Workflow {i+1}"

                # Create simple workflow definition
                nodes = [
                    {
                        'id': str(uuid.uuid4()),
                        'type': 'webhook_trigger',
                        'position': {'x': 100, 'y': 100},
                        'properties': {'config': {}}
                    },
                    {
                        'id': str(uuid.uuid4()),
                        'type': 'http_request',
                        'position': {'x': 300, 'y': 100},
                        'properties': {'url': 'https://api.example.com', 'method': 'GET'}
                    }
                ]

                connections = [
                    {
                        'id': str(uuid.uuid4()),
                        'source': nodes[0]['id'],
                        'target': nodes[1]['id'],
                        'sourcePort': 'output',
                        'targetPort': 'input'
                    }
                ]

                workflow = Workflow.objects.create(
                    name=workflow_name,
                    description=fake.text(max_nb_chars=200),
                    organization=random.choice(self.organizations),
                    category=random.choice(self.categories) if self.categories else None,
                    status=random.choice(['draft', 'active', 'paused']),
                    trigger_type=random.choice(['manual', 'webhook', 'schedule']),
                    nodes=nodes,
                    connections=connections,
                    variables={'api_key': 'test_key'},
                    tags=['test', 'sample'],
                    created_by=random.choice(self.users),
                    updated_by=random.choice(self.users)
                )
                self.workflows.append(workflow)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating workflow: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(self.workflows)} workflows'))

    def create_executions(self, count):
        """Create sample executions"""
        if 'executions' not in self.available_models or not self.workflows:
            self.stdout.write(self.style.WARNING('⚠️  Skipping executions - missing dependencies'))
            return

        self.stdout.write(f'⚡ Creating {count} executions...')

        ExecutionQueue = self.available_models['executions']['ExecutionQueue']

        for i in range(count):
            try:
                workflow = random.choice(self.workflows)
                status = random.choice(['pending', 'running', 'completed', 'failed'])

                execution = ExecutionQueue.objects.create(
                    workflow=workflow,
                    execution_id=f"sample-{uuid.uuid4().hex[:8]}",
                    status=status,
                    trigger_type='manual',
                    triggered_by=random.choice(self.users),
                    input_data={'test': 'data'},
                    priority='normal'
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating execution: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created executions'))

    def create_analytics_dashboards(self, count):
        """Create sample analytics dashboards"""
        if 'analytics' not in self.available_models or not self.organizations:
            self.stdout.write(self.style.WARNING('⚠️  Skipping dashboards - missing dependencies'))
            return

        self.stdout.write(f'📊 Creating {count} analytics dashboards...')

        AnalyticsDashboard = self.available_models['analytics']['AnalyticsDashboard']
        AnalyticsWidget = self.available_models['analytics']['AnalyticsWidget']

        for i in range(count):
            try:
                dashboard = AnalyticsDashboard.objects.create(
                    organization=random.choice(self.organizations),
                    name=f"Sample Dashboard {i+1}",
                    description=fake.text(max_nb_chars=150),
                    dashboard_type='custom',
                    layout={'grid': {'rows': 12, 'cols': 12}},
                    created_by=random.choice(self.users)
                )

                # Create a sample widget
                AnalyticsWidget.objects.create(
                    dashboard=dashboard,
                    title="Sample Widget",
                    widget_type='chart',
                    chart_type='line',
                    query_config={'metric': 'executions', 'timeframe': '7d'},
                    position_x=0,
                    position_y=0,
                    width=6,
                    height=4
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Error creating dashboard: {e}'))

        self.stdout.write(self.style.SUCCESS(f'✅ Created analytics dashboards'))

    def print_summary(self):
        """Print generation summary"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('✅ SAFE SAMPLE DATA GENERATION COMPLETED!'))
        self.stdout.write('='*60)

        self.stdout.write('\nGenerated:')
        self.stdout.write(f'  👤 {User.objects.count()} users')

        if 'organizations' in self.available_models:
            self.stdout.write(f'  🏢 {self.available_models["organizations"]["Organization"].objects.count()} organizations')

        if 'workflows' in self.available_models:
            self.stdout.write(f'  🔄 {self.available_models["workflows"]["Workflow"].objects.count()} workflows')

        if 'nodes' in self.available_models:
            self.stdout.write(f'  🧩 {self.available_models["nodes"]["NodeType"].objects.count()} node types')

        if 'executions' in self.available_models:
            self.stdout.write(f'  ⚡ {self.available_models["executions"]["ExecutionQueue"].objects.count()} executions')

        if 'analytics' in self.available_models:
            self.stdout.write(f'  📊 {self.available_models["analytics"]["AnalyticsDashboard"].objects.count()} dashboards')

        self.stdout.write('\n🎯 Login credentials:')
        self.stdout.write('  Admin: admin / admin123')
        self.stdout.write('  Regular users: <username> / testpass123')
        self.stdout.write('\n' + '='*60)