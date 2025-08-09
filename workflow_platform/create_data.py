#!/usr/bin/env python3
"""
Sample Data Generator for Workflow Platform
Creates realistic test data for all models in the system
"""

import os
import sys
import django
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from faker import Faker
import random
import uuid
import json

# Setup Django environment
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'workflow_platform.settings.development')

try:
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    print("Make sure you're running this script from the Django project root directory")
    print("and that the virtual environment is activated.")
    sys.exit(1)

# Import models after Django setup
from apps.organizations.models import Organization, OrganizationMembership
from apps.workflows.models import Workflow, WorkflowExecution, WorkflowTemplate, WorkflowCategory, WorkflowComment
from apps.nodes.models import NodeType, NodeCredential, NodeTypeCategory
from apps.executions.models import ExecutionQueue, ExecutionHistory, ExecutionSchedule
from apps.analytics.models import AnalyticsDashboard, AnalyticsWidget, AnalyticsReport

fake = Faker()


class SampleDataGenerator:
    def __init__(self):
        self.users = []
        self.organizations = []
        self.workflows = []
        self.node_types = []
        self.categories = []

    def create_users(self, count=20):
        """Create sample users"""
        print(f"Creating {count} users...")

        for i in range(count):
            user = User.objects.create_user(
                username=fake.user_name(),
                email=fake.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                password='testpass123'
            )
            self.users.append(user)

        # Create admin user
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            password='admin123'
        )
        self.users.append(admin_user)

        print(f"✓ Created {len(self.users)} users")
        return self.users

    def create_organizations(self, count=5):
        """Create sample organizations"""
        print(f"Creating {count} organizations...")

        org_names = [
            'TechCorp Solutions', 'DataFlow Industries', 'AutoMate Systems',
            'CloudWorks Inc', 'ProcessPro Ltd', 'FlowTech Dynamics'
        ]

        for i in range(count):
            org = Organization.objects.create(
                name=org_names[i] if i < len(org_names) else fake.company(),
                slug=fake.slug(),
                description=fake.text(max_nb_chars=200),
                plan=random.choice(['free', 'pro', 'enterprise']),
                settings={
                    'max_workflows': random.randint(50, 500),
                    'max_executions_per_month': random.randint(1000, 10000),
                    'retention_days': random.choice([30, 90, 365])
                }
            )
            self.organizations.append(org)

            # Add members to organization
            members = random.sample(self.users, k=random.randint(2, 6))
            for j, user in enumerate(members):
                role = 'owner' if j == 0 else random.choice(['admin', 'member'])
                OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    role=role
                )

        print(f"✓ Created {len(self.organizations)} organizations")
        return self.organizations

    def create_workflow_categories(self):
        """Create workflow categories"""
        print("Creating workflow categories...")

        categories_data = [
            {'name': 'Data Processing', 'description': 'ETL and data transformation workflows', 'icon': 'database',
             'color': '#3B82F6'},
            {'name': 'Automation', 'description': 'Business process automation', 'icon': 'cog', 'color': '#10B981'},
            {'name': 'Integration', 'description': 'API and system integrations', 'icon': 'link', 'color': '#F59E0B'},
            {'name': 'Notifications', 'description': 'Alert and notification workflows', 'icon': 'bell',
             'color': '#EF4444'},
            {'name': 'Analytics', 'description': 'Data analysis and reporting', 'icon': 'chart-bar',
             'color': '#8B5CF6'},
            {'name': 'Security', 'description': 'Security and compliance workflows', 'icon': 'shield',
             'color': '#6B7280'}
        ]

        for cat_data in categories_data:
            category = WorkflowCategory.objects.create(**cat_data)
            self.categories.append(category)

        print(f"✓ Created {len(self.categories)} workflow categories")
        return self.categories

    def create_node_type_categories(self):
        """Create node type categories"""
        print("Creating node type categories...")

        node_categories = [
            {'name': 'Triggers', 'description': 'Workflow trigger nodes', 'icon': 'play', 'color': '#10B981'},
            {'name': 'Actions', 'description': 'Action execution nodes', 'icon': 'lightning', 'color': '#3B82F6'},
            {'name': 'Logic', 'description': 'Logic and control flow nodes', 'icon': 'branch', 'color': '#F59E0B'},
            {'name': 'Data', 'description': 'Data manipulation nodes', 'icon': 'database', 'color': '#8B5CF6'},
            {'name': 'Communication', 'description': 'Communication and messaging', 'icon': 'mail', 'color': '#EF4444'},
            {'name': 'Utilities', 'description': 'Utility and helper nodes', 'icon': 'tools', 'color': '#6B7280'}
        ]

        for cat_data in node_categories:
            NodeTypeCategory.objects.create(**cat_data)

        print("✓ Created node type categories")

    def create_node_types(self, count=30):
        """Create sample node types"""
        print(f"Creating {count} node types...")

        node_templates = [
            # Triggers
            {'node_type': 'webhook_trigger', 'display_name': 'Webhook Trigger', 'category': 'triggers'},
            {'node_type': 'schedule_trigger', 'display_name': 'Schedule Trigger', 'category': 'triggers'},
            {'node_type': 'email_trigger', 'display_name': 'Email Trigger', 'category': 'triggers'},

            # Actions
            {'node_type': 'http_request', 'display_name': 'HTTP Request', 'category': 'actions'},
            {'node_type': 'send_email', 'display_name': 'Send Email', 'category': 'actions'},
            {'node_type': 'slack_message', 'display_name': 'Send Slack Message', 'category': 'actions'},
            {'node_type': 'discord_webhook', 'display_name': 'Discord Webhook', 'category': 'actions'},

            # Logic
            {'node_type': 'if_condition', 'display_name': 'If Condition', 'category': 'logic'},
            {'node_type': 'switch_case', 'display_name': 'Switch Case', 'category': 'logic'},
            {'node_type': 'loop', 'display_name': 'Loop', 'category': 'logic'},
            {'node_type': 'delay', 'display_name': 'Delay', 'category': 'logic'},

            # Data
            {'node_type': 'json_parser', 'display_name': 'JSON Parser', 'category': 'data'},
            {'node_type': 'csv_reader', 'display_name': 'CSV Reader', 'category': 'data'},
            {'node_type': 'data_transformer', 'display_name': 'Data Transformer', 'category': 'data'},
            {'node_type': 'database_query', 'display_name': 'Database Query', 'category': 'data'},

            # Communication
            {'node_type': 'sms_sender', 'display_name': 'SMS Sender', 'category': 'communication'},
            {'node_type': 'teams_message', 'display_name': 'Teams Message', 'category': 'communication'},

            # Utilities
            {'node_type': 'code_executor', 'display_name': 'Code Executor', 'category': 'utilities'},
            {'node_type': 'file_processor', 'display_name': 'File Processor', 'category': 'utilities'},
            {'node_type': 'hash_generator', 'display_name': 'Hash Generator', 'category': 'utilities'}
        ]

        for template in node_templates:
            node_type = NodeType.objects.create(
                node_type=template['node_type'],
                display_name=template['display_name'],
                description=fake.text(max_nb_chars=150),
                category=template['category'],
                source='built_in',
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

        print(f"✓ Created {len(self.node_types)} node types")
        return self.node_types

    def create_workflows(self, count=50):
        """Create sample workflows"""
        print(f"Creating {count} workflows...")

        workflow_templates = [
            'User Registration Automation', 'Order Processing Pipeline', 'Data Backup Workflow',
            'Email Campaign Automation', 'Customer Feedback Processing', 'Invoice Generation',
            'Lead Scoring Automation', 'Social Media Monitoring', 'File Sync Workflow',
            'Database Cleanup Process', 'Report Generation Pipeline', 'Alert Management',
            'Content Moderation Flow', 'Payment Processing', 'Inventory Management'
        ]

        for i in range(count):
            workflow_name = workflow_templates[i % len(workflow_templates)]
            if i >= len(workflow_templates):
                workflow_name += f" {i // len(workflow_templates) + 1}"

            # Create workflow definition
            nodes = []
            connections = []

            # Add a trigger node
            trigger_node = {
                'id': str(uuid.uuid4()),
                'type': random.choice(['webhook_trigger', 'schedule_trigger']),
                'position': {'x': 100, 'y': 100},
                'properties': {'config': {}}
            }
            nodes.append(trigger_node)

            # Add 2-5 action nodes
            for j in range(random.randint(2, 5)):
                node = {
                    'id': str(uuid.uuid4()),
                    'type': random.choice([nt.node_type for nt in self.node_types]),
                    'position': {'x': 200 + j * 150, 'y': 100 + random.randint(-50, 50)},
                    'properties': {'config': {}}
                }
                nodes.append(node)

                # Connect to previous node
                if j == 0:
                    source_id = trigger_node['id']
                else:
                    source_id = nodes[-2]['id']

                connection = {
                    'id': str(uuid.uuid4()),
                    'source': source_id,
                    'target': node['id'],
                    'sourcePort': 'output',
                    'targetPort': 'input'
                }
                connections.append(connection)

            workflow = Workflow.objects.create(
                name=workflow_name,
                description=fake.text(max_nb_chars=200),
                organization=random.choice(self.organizations),
                category=random.choice(self.categories),
                status=random.choice(['draft', 'active', 'paused']),
                trigger_type=random.choice(['manual', 'webhook', 'schedule']),
                nodes=nodes,
                connections=connections,
                variables={
                    'api_url': 'https://api.example.com',
                    'retry_count': 3,
                    'timeout': 30
                },
                tags=[fake.word() for _ in range(random.randint(1, 4))],
                is_public=random.choice([True, False]),
                created_by=random.choice(self.users),
                updated_by=random.choice(self.users)
            )
            self.workflows.append(workflow)

        print(f"✓ Created {len(self.workflows)} workflows")
        return self.workflows

    def create_workflow_executions(self, count=200):
        """Create sample workflow executions"""
        print(f"Creating {count} workflow executions...")

        statuses = ['pending', 'running', 'completed', 'failed', 'cancelled']

        for i in range(count):
            workflow = random.choice(self.workflows)
            status = random.choice(statuses)

            # Set execution times based on status
            created_at = fake.date_time_between(start_date='-30d', end_date='now', tzinfo=timezone.utc)
            started_at = None
            completed_at = None

            if status in ['running', 'completed', 'failed', 'cancelled']:
                started_at = created_at + timedelta(seconds=random.randint(1, 60))

                if status in ['completed', 'failed', 'cancelled']:
                    completed_at = started_at + timedelta(seconds=random.randint(10, 300))

            execution = WorkflowExecution.objects.create(
                workflow=workflow,
                execution_id=str(uuid.uuid4()),
                status=status,
                trigger_type=workflow.trigger_type,
                trigger_source=random.choice(['manual', 'api', 'webhook', 'schedule']),
                triggered_by=random.choice(self.users),
                input_data={'test': 'data', 'value': random.randint(1, 100)},
                output_data={'result': 'success'} if status == 'completed' else {},
                error_message=fake.sentence() if status == 'failed' else '',
                nodes_executed=random.randint(1, len(workflow.nodes)),
                nodes_failed=random.randint(0, 2) if status == 'failed' else 0,
                memory_usage_mb=random.randint(10, 200),
                cpu_usage_percent=random.randint(5, 95),
                created_at=created_at,
                started_at=started_at,
                completed_at=completed_at
            )

            # Update workflow stats
            workflow.total_executions += 1
            if status == 'completed':
                workflow.successful_executions += 1
            elif status == 'failed':
                workflow.failed_executions += 1

            workflow.last_executed_at = created_at
            workflow.save()

        print(f"✓ Created {count} workflow executions")

    def create_node_credentials(self, count=15):
        """Create sample node credentials"""
        print(f"Creating {count} node credentials...")

        credential_templates = [
            {'name': 'Slack Bot Token', 'credential_type': 'api_key', 'service_name': 'slack'},
            {'name': 'Gmail OAuth', 'credential_type': 'oauth2', 'service_name': 'gmail'},
            {'name': 'AWS Access Key', 'credential_type': 'api_key', 'service_name': 'aws'},
            {'name': 'Database Connection', 'credential_type': 'database', 'service_name': 'postgresql'},
            {'name': 'Discord Webhook', 'credential_type': 'api_key', 'service_name': 'discord'},
            {'name': 'Stripe API Key', 'credential_type': 'api_key', 'service_name': 'stripe'},
            {'name': 'GitHub Token', 'credential_type': 'bearer_token', 'service_name': 'github'},
            {'name': 'SendGrid API', 'credential_type': 'api_key', 'service_name': 'sendgrid'},
            {'name': 'Twilio Auth', 'credential_type': 'basic_auth', 'service_name': 'twilio'},
            {'name': 'Azure Storage', 'credential_type': 'api_key', 'service_name': 'azure'}
        ]

        for i, template in enumerate(credential_templates):
            if i >= count:
                break

            from apps.core.utils import encrypt_data

            # Sample credential data (would be encrypted in real usage)
            credential_data = {
                'api_key': fake.sha256(),
                'secret': fake.sha256(),
                'region': random.choice(['us-east-1', 'eu-west-1', 'ap-south-1'])
            }

            NodeCredential.objects.create(
                organization=random.choice(self.organizations),
                name=template['name'],
                credential_type=template['credential_type'],
                service_name=template['service_name'],
                description=fake.text(max_nb_chars=100),
                encrypted_data=json.dumps(credential_data),  # In real app, this would be encrypted
                encryption_key_id=fake.uuid4(),
                created_by=random.choice(self.users)
            )

        print(f"✓ Created {count} node credentials")

    def create_analytics_dashboards(self, count=10):
        """Create sample analytics dashboards"""
        print(f"Creating {count} analytics dashboards...")

        dashboard_templates = [
            'Workflow Performance Overview', 'Execution Analytics', 'Error Analysis Dashboard',
            'Usage Statistics', 'Cost Analysis', 'Performance Trends', 'User Activity',
            'System Health Monitor', 'Security Dashboard', 'Custom Metrics'
        ]

        for i in range(count):
            dashboard = AnalyticsDashboard.objects.create(
                organization=random.choice(self.organizations),
                name=dashboard_templates[i % len(dashboard_templates)],
                description=fake.text(max_nb_chars=150),
                dashboard_type=random.choice(['overview', 'detailed', 'custom']),
                layout_config={
                    'grid': {'rows': 12, 'cols': 12},
                    'widgets': []
                },
                created_by=random.choice(self.users)
            )

            # Create widgets for dashboard
            for j in range(random.randint(2, 6)):
                AnalyticsWidget.objects.create(
                    dashboard=dashboard,
                    title=f"Widget {j + 1}",
                    widget_type=random.choice(['chart', 'metric', 'table']),
                    chart_type=random.choice(['line', 'bar', 'pie', 'doughnut']),
                    query_config={'metric': 'executions', 'timeframe': '7d'},
                    position_x=random.randint(0, 8),
                    position_y=random.randint(0, 8),
                    width=random.randint(2, 6),
                    height=random.randint(2, 4)
                )

        print(f"✓ Created {count} analytics dashboards")

    def create_execution_schedules(self, count=20):
        """Create sample execution schedules"""
        print(f"Creating {count} execution schedules...")

        for i in range(count):
            workflow = random.choice(self.workflows)

            ExecutionSchedule.objects.create(
                workflow=workflow,
                name=f"Schedule for {workflow.name}",
                cron_expression=random.choice([
                    '0 9 * * *',  # Daily at 9 AM
                    '0 */6 * * *',  # Every 6 hours
                    '0 0 * * 0',  # Weekly on Sunday
                    '0 0 1 * *',  # Monthly on 1st
                    '*/15 * * * *'  # Every 15 minutes
                ]),
                timezone='UTC',
                is_active=random.choice([True, False]),
                created_by=random.choice(self.users)
            )

        print(f"✓ Created {count} execution schedules")

    def generate_all_data(self):
        """Generate all sample data"""
        print("🚀 Starting sample data generation...")
        print("=" * 50)

        # Create base data
        self.create_users(20)
        self.create_organizations(5)
        self.create_workflow_categories()
        self.create_node_type_categories()

        # Create workflow-related data
        self.create_node_types(25)
        self.create_workflows(50)
        self.create_workflow_executions(200)

        # Create supporting data
        self.create_node_credentials(15)
        self.create_analytics_dashboards(8)
        self.create_execution_schedules(20)

        print("=" * 50)
        print("✅ Sample data generation completed!")
        print("\nGenerated:")
        print(f"  👤 {User.objects.count()} users")
        print(f"  🏢 {Organization.objects.count()} organizations")
        print(f"  🔄 {Workflow.objects.count()} workflows")
        print(f"  ⚡ {WorkflowExecution.objects.count()} executions")
        print(f"  🧩 {NodeType.objects.count()} node types")
        print(f"  🔐 {NodeCredential.objects.count()} credentials")
        print(f"  📊 {AnalyticsDashboard.objects.count()} dashboards")
        print(f"  ⏰ {ExecutionSchedule.objects.count()} schedules")

        print("\n🎯 Login credentials:")
        print("  Admin: admin / admin123")
        print("  Regular users: <username> / testpass123")


if __name__ == '__main__':
    generator = SampleDataGenerator()
    generator.generate_all_data()