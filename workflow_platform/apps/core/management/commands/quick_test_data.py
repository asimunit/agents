"""
Quick Test Data Command - Creates minimal test data for immediate testing
Place this file in: apps/core/management/commands/quick_test_data.py
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from faker import Faker
import random
import uuid

fake = Faker()


class Command(BaseCommand):
    help = 'Create minimal test data quickly'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Creating quick test data...'))

        # Create admin user
        admin, created = User.objects.get_or_create(
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
            admin.set_password('admin123')
            admin.save()
            self.stdout.write('✅ Created admin user')
        else:
            self.stdout.write('ℹ️ Admin user already exists')

        # Create test user
        test_user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User'
            }
        )
        if created:
            test_user.set_password('testpass123')
            test_user.save()
            self.stdout.write('✅ Created test user')
        else:
            self.stdout.write('ℹ️ Test user already exists')

        # Try to create organization
        try:
            from apps.organizations.models import Organization, OrganizationMember

            org, created = Organization.objects.get_or_create(
                name='Test Organization',
                defaults={
                    'slug': 'test-org',
                    'description': 'Test organization for development',
                    'plan': 'pro',
                    'created_by': admin
                }
            )

            if created:
                # Add admin as owner
                OrganizationMember.objects.get_or_create(
                    organization=org,
                    user=admin,
                    defaults={
                        'role': 'owner',
                        'status': 'active',
                        'joined_at': timezone.now()
                    }
                )

                # Add test user as member
                OrganizationMember.objects.get_or_create(
                    organization=org,
                    user=test_user,
                    defaults={
                        'role': 'member',
                        'status': 'active',
                        'joined_at': timezone.now()
                    }
                )

                self.stdout.write('✅ Created test organization with members')
            else:
                self.stdout.write('ℹ️ Test organization already exists')

        except ImportError:
            self.stdout.write('⚠️ Organizations app not available')

        # Try to create node categories
        try:
            from apps.nodes.models import NodeCategory

            categories = [
                {'name': 'Actions', 'display_name': 'Actions', 'description': 'Action nodes', 'icon': 'lightning',
                 'color': '#3B82F6'},
                {'name': 'Logic', 'display_name': 'Logic', 'description': 'Logic nodes', 'icon': 'branch',
                 'color': '#F59E0B'},
            ]

            for cat_data in categories:
                category, created = NodeCategory.objects.get_or_create(
                    name=cat_data['name'],
                    defaults=cat_data
                )
                if created:
                    self.stdout.write(f'✅ Created node category: {category.name}')

        except ImportError:
            self.stdout.write('⚠️ Node categories not available')

        # Try to create simple workflow
        try:
            from apps.workflows.models import Workflow, WorkflowCategory
            from apps.organizations.models import Organization

            # Create workflow category
            wf_category, created = WorkflowCategory.objects.get_or_create(
                name='Test',
                defaults={
                    'description': 'Test workflows',
                    'icon': 'test',
                    'color': '#6366f1'
                }
            )

            # Get organization
            org = Organization.objects.first()
            if org:
                workflow, created = Workflow.objects.get_or_create(
                    name='Test Workflow',
                    defaults={
                        'description': 'Simple test workflow',
                        'organization': org,
                        'category': wf_category,
                        'status': 'active',
                        'trigger_type': 'manual',
                        'nodes': [
                            {
                                'id': str(uuid.uuid4()),
                                'type': 'http_request',
                                'position': {'x': 100, 'y': 100},
                                'properties': {'url': 'https://api.example.com'}
                            }
                        ],
                        'connections': [],
                        'variables': {},
                        'tags': ['test'],
                        'created_by': admin,
                        'updated_by': admin
                    }
                )

                if created:
                    self.stdout.write('✅ Created test workflow')
                else:
                    self.stdout.write('ℹ️ Test workflow already exists')

        except ImportError:
            self.stdout.write('⚠️ Workflows not available')

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('✅ QUICK TEST DATA CREATED!'))
        self.stdout.write('=' * 50)
        self.stdout.write('\n🎯 Login credentials:')
        self.stdout.write('  Admin: admin / admin123')
        self.stdout.write('  Test User: testuser / testpass123')
        self.stdout.write('\n📊 Summary:')
        self.stdout.write(f'  Users: {User.objects.count()}')

        try:
            from apps.organizations.models import Organization
            self.stdout.write(f'  Organizations: {Organization.objects.count()}')
        except ImportError:
            pass

        try:
            from apps.workflows.models import Workflow
            self.stdout.write(f'  Workflows: {Workflow.objects.count()}')
        except ImportError:
            pass

        self.stdout.write('\n🚀 Ready to test your API!')