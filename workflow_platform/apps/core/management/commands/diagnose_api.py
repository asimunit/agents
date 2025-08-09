"""
API Diagnostic Command - Check system health and fix common issues
Place this file in: apps/core/management/commands/diagnose_api.py
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.urls import reverse
from django.test import Client
from django.utils import timezone
import json


class Command(BaseCommand):
    help = 'Diagnose API issues and check system health'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Starting API diagnostics...'))

        # Check basic setup
        self.check_basic_setup()

        # Check database
        self.check_database()

        # Check models
        self.check_models()

        # Check API endpoints
        self.check_api_endpoints()

        # Check authentication
        self.check_authentication()

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✅ DIAGNOSTICS COMPLETED'))
        self.stdout.write('=' * 60)

    def check_basic_setup(self):
        """Check basic Django setup"""
        self.stdout.write('\n🔧 Checking basic setup...')

        # Check if admin user exists
        try:
            admin_user = User.objects.get(username='admin')
            self.stdout.write(f'✅ Admin user exists: {admin_user.email}')
        except User.DoesNotExist:
            self.stdout.write('⚠️  Admin user not found')

        # Check total users
        user_count = User.objects.count()
        self.stdout.write(f'👤 Total users: {user_count}')

    def check_database(self):
        """Check database connectivity"""
        self.stdout.write('\n💾 Checking database...')

        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.stdout.write('✅ Database connection: OK')
        except Exception as e:
            self.stdout.write(f'❌ Database connection: {e}')

    def check_models(self):
        """Check model availability and data"""
        self.stdout.write('\n📊 Checking models...')

        # Check organizations
        try:
            from apps.organizations.models import Organization, OrganizationMember
            org_count = Organization.objects.count()
            member_count = OrganizationMember.objects.count()
            self.stdout.write(f'✅ Organizations: {org_count} orgs, {member_count} members')
        except Exception as e:
            self.stdout.write(f'❌ Organizations: {e}')

        # Check workflows
        try:
            from apps.workflows.models import Workflow, WorkflowCategory
            workflow_count = Workflow.objects.count()
            category_count = WorkflowCategory.objects.count()
            self.stdout.write(f'✅ Workflows: {workflow_count} workflows, {category_count} categories')
        except Exception as e:
            self.stdout.write(f'❌ Workflows: {e}')

        # Check nodes
        try:
            from apps.nodes.models import NodeType, NodeCategory
            node_count = NodeType.objects.count()
            node_cat_count = NodeCategory.objects.count()
            self.stdout.write(f'✅ Nodes: {node_count} types, {node_cat_count} categories')
        except Exception as e:
            self.stdout.write(f'❌ Nodes: {e}')

        # Check executions
        try:
            from apps.executions.models import ExecutionQueue, ExecutionHistory
            queue_count = ExecutionQueue.objects.count()
            history_count = ExecutionHistory.objects.count()
            self.stdout.write(f'✅ Executions: {queue_count} queued, {history_count} history')
        except Exception as e:
            self.stdout.write(f'❌ Executions: {e}')

    def check_api_endpoints(self):
        """Check key API endpoints"""
        self.stdout.write('\n🌐 Checking API endpoints...')

        client = Client()

        # Test health endpoint
        try:
            response = client.get('/health/')
            if response.status_code == 200:
                self.stdout.write('✅ Health endpoint: OK')
            else:
                self.stdout.write(f'⚠️  Health endpoint: {response.status_code}')
        except Exception as e:
            self.stdout.write(f'❌ Health endpoint: {e}')

        # Test API schema
        schema_urls = ['/api/schema/', '/schema/']
        for url in schema_urls:
            try:
                response = client.get(url)
                if response.status_code == 200:
                    self.stdout.write(f'✅ API schema: OK ({url})')
                    break
            except:
                continue
        else:
            self.stdout.write('⚠️  API schema: Not available')

        # Test docs
        docs_urls = ['/api/docs/', '/docs/']
        for url in docs_urls:
            try:
                response = client.get(url)
                if response.status_code in [200, 406]:  # 406 is expected for browser requests
                    self.stdout.write(f'✅ API docs: Available ({url})')
                    break
            except:
                continue
        else:
            self.stdout.write('⚠️  API docs: Not available')

    def check_authentication(self):
        """Check authentication setup"""
        self.stdout.write('\n🔐 Checking authentication...')

        client = Client()

        # Test login endpoint
        try:
            login_data = {
                'username': 'admin',
                'password': 'admin123'
            }
            response = client.post('/api/v1/auth/login/',
                                   data=json.dumps(login_data),
                                   content_type='application/json')

            if response.status_code == 200:
                self.stdout.write('✅ Authentication login: OK')

                # Try to access protected endpoint
                data = response.json()
                if 'access' in data:
                    token = data['access']
                    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

                    protected_response = client.get('/api/v1/workflows/', **headers)
                    if protected_response.status_code == 200:
                        self.stdout.write('✅ Protected endpoint access: OK')
                    else:
                        self.stdout.write(f'⚠️  Protected endpoint: {protected_response.status_code}')
                else:
                    self.stdout.write('⚠️  Login response missing access token')
            else:
                self.stdout.write(f'❌ Authentication login: {response.status_code}')

        except Exception as e:
            self.stdout.write(f'❌ Authentication: {e}')

        # Check JWT settings
        try:
            from django.conf import settings
            if hasattr(settings, 'SIMPLE_JWT'):
                self.stdout.write('✅ JWT settings: Configured')
            else:
                self.stdout.write('⚠️  JWT settings: Not found')
        except Exception as e:
            self.stdout.write(f'❌ JWT settings: {e}')

    def check_organization_memberships(self):
        """Check organization membership issues"""
        self.stdout.write('\n🏢 Checking organization memberships...')

        try:
            from apps.organizations.models import OrganizationMember

            # Check admin user membership
            admin_user = User.objects.get(username='admin')
            memberships = OrganizationMember.objects.filter(user=admin_user, status='active')

            if memberships.exists():
                self.stdout.write(f'✅ Admin has {memberships.count()} active memberships')
                for membership in memberships:
                    self.stdout.write(f'   - {membership.organization.name} ({membership.role})')
            else:
                self.stdout.write('⚠️  Admin has no active organization memberships')

                # Try to fix by creating a membership
                from apps.organizations.models import Organization
                if Organization.objects.exists():
                    org = Organization.objects.first()
                    OrganizationMember.objects.get_or_create(
                        organization=org,
                        user=admin_user,
                        defaults={
                            'role': 'owner',
                            'status': 'active',
                            'joined_at': timezone.now()
                        }
                    )
                    self.stdout.write('🔧 Created admin membership in first organization')

        except Exception as e:
            self.stdout.write(f'❌ Organization memberships: {e}')