#!/usr/bin/env python3
"""
Comprehensive API Test Suite for Workflow Platform
Tests all endpoints with realistic scenarios and data validation
"""

import requests
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sys
import argparse
from dataclasses import dataclass
from urllib.parse import urljoin
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    endpoint: str
    method: str
    status_code: int
    response_time: float
    success: bool
    error_message: Optional[str] = None
    response_data: Optional[Dict] = None


class WorkflowPlatformAPITester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

        # Test data storage
        self.test_results: List[TestResult] = []
        self.test_data = {
            'users': [],
            'organizations': [],
            'workflows': [],
            'executions': [],
            'node_types': [],
            'credentials': [],
            'dashboards': []
        }

        # Authentication tokens
        self.access_token = None
        self.refresh_token = None
        self.current_user = None

    def make_request(self, method: str, endpoint: str, **kwargs) -> TestResult:
        """Make HTTP request and record results"""
        url = urljoin(self.base_url, endpoint.lstrip('/'))

        start_time = time.time()
        try:
            response = self.session.request(method, url, **kwargs)
            response_time = time.time() - start_time

            try:
                response_data = response.json()
            except ValueError:
                response_data = {'raw_response': response.text}

            success = 200 <= response.status_code < 300
            error_message = None if success else f"HTTP {response.status_code}: {response_data.get('detail', 'Unknown error')}"

            result = TestResult(
                endpoint=endpoint,
                method=method,
                status_code=response.status_code,
                response_time=response_time,
                success=success,
                error_message=error_message,
                response_data=response_data
            )

        except requests.RequestException as e:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=str(e)
            )

        self.test_results.append(result)
        return result

    def authenticate(self, username: str = "admin", password: str = "admin123"):
        """Authenticate user and set authorization header"""
        logger.info(f"🔐 Authenticating user: {username}")

        auth_data = {
            "username": username,
            "password": password
        }

        result = self.make_request('POST', '/api/v1/auth/login/', json=auth_data)

        if result.success and result.response_data:
            self.access_token = result.response_data.get('access')
            self.refresh_token = result.response_data.get('refresh')
            self.current_user = result.response_data.get('user')

            if self.access_token:
                self.session.headers['Authorization'] = f'Bearer {self.access_token}'
                logger.info("✅ Authentication successful")
                return True

        logger.error("❌ Authentication failed")
        return False

    def test_health_check(self):
        """Test health check endpoint"""
        logger.info("🏥 Testing health check...")
        result = self.make_request('GET', '/health/')
        return result.success

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        logger.info("🔑 Testing authentication endpoints...")

        # Test user registration
        registration_data = {
            "username": f"testuser_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "password": "testpass123",
            "first_name": "Test",
            "last_name": "User"
        }

        result = self.make_request('POST', '/api/v1/auth/register/', json=registration_data)
        if result.success:
            self.test_data['users'].append(result.response_data)

        # Test login (already done in authenticate)

        # Test token refresh
        if self.refresh_token:
            refresh_data = {"refresh": self.refresh_token}
            self.make_request('POST', '/api/v1/auth/token/refresh/', json=refresh_data)

        # Test user profile
        self.make_request('GET', '/api/v1/auth/profile/')

        # Test logout
        self.make_request('POST', '/api/v1/auth/logout/')

    def test_organization_endpoints(self):
        """Test organization management endpoints"""
        logger.info("🏢 Testing organization endpoints...")

        # List organizations
        result = self.make_request('GET', '/api/v1/organizations/')
        if result.success and result.response_data.get('results'):
            self.test_data['organizations'] = result.response_data['results']

        # Create organization
        org_data = {
            "name": f"Test Org {uuid.uuid4().hex[:8]}",
            "description": "Test organization for API testing",
            "plan": "pro"
        }

        result = self.make_request('POST', '/api/v1/organizations/', json=org_data)
        if result.success:
            org_id = result.response_data['id']
            self.test_data['organizations'].append(result.response_data)

            # Get organization details
            self.make_request('GET', f'/api/v1/organizations/{org_id}/')

            # Update organization
            update_data = {"description": "Updated description"}
            self.make_request('PATCH', f'/api/v1/organizations/{org_id}/', json=update_data)

            # Test organization members
            self.make_request('GET', f'/api/v1/organizations/{org_id}/members/')

            # Test organization statistics
            self.make_request('GET', f'/api/v1/organizations/{org_id}/stats/')

    def test_workflow_endpoints(self):
        """Test workflow management endpoints"""
        logger.info("🔄 Testing workflow endpoints...")

        # List workflows
        result = self.make_request('GET', '/api/v1/workflows/')
        if result.success and result.response_data.get('results'):
            self.test_data['workflows'] = result.response_data['results']

        # Create workflow
        workflow_data = {
            "name": f"Test Workflow {uuid.uuid4().hex[:8]}",
            "description": "Test workflow for API testing",
            "trigger_type": "manual",
            "nodes": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "webhook_trigger",
                    "position": {"x": 100, "y": 100},
                    "properties": {"config": {}}
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "http_request",
                    "position": {"x": 300, "y": 100},
                    "properties": {"url": "https://api.example.com", "method": "GET"}
                }
            ],
            "connections": [
                {
                    "id": str(uuid.uuid4()),
                    "source": "node1",
                    "target": "node2",
                    "sourcePort": "output",
                    "targetPort": "input"
                }
            ],
            "variables": {"api_key": "test_key"},
            "tags": ["test", "api"]
        }

        result = self.make_request('POST', '/api/v1/workflows/', json=workflow_data)
        if result.success:
            workflow_id = result.response_data['id']
            self.test_data['workflows'].append(result.response_data)

            # Get workflow details
            self.make_request('GET', f'/api/v1/workflows/{workflow_id}/')

            # Update workflow
            update_data = {"description": "Updated workflow description"}
            self.make_request('PATCH', f'/api/v1/workflows/{workflow_id}/', json=update_data)

            # Test workflow execution
            execution_data = {"input_data": {"test": "value"}}
            result = self.make_request('POST', f'/api/v1/workflows/{workflow_id}/execute/', json=execution_data)
            if result.success:
                execution_id = result.response_data.get('execution_id')
                if execution_id:
                    self.test_data['executions'].append(result.response_data)

            # Test workflow validation
            self.make_request('POST', f'/api/v1/workflows/{workflow_id}/validate/')

            # Test workflow clone
            clone_data = {"name": f"Cloned Workflow {uuid.uuid4().hex[:8]}"}
            self.make_request('POST', f'/api/v1/workflows/{workflow_id}/clone/', json=clone_data)

            # Test workflow export
            self.make_request('GET', f'/api/v1/workflows/{workflow_id}/export/')

            # Test workflow analytics
            self.make_request('GET', f'/api/v1/workflows/{workflow_id}/analytics/')

            # Test workflow comments
            comment_data = {"content": "Test comment for workflow"}
            self.make_request('POST', f'/api/v1/workflows/{workflow_id}/comments/', json=comment_data)

            # List workflow executions
            self.make_request('GET', f'/api/v1/workflows/{workflow_id}/executions/')

        # Test workflow categories
        self.make_request('GET', '/api/v1/workflows/categories/')

        # Test workflow templates
        self.make_request('GET', '/api/v1/workflows/templates/')

        # Test workflow search
        self.make_request('GET', '/api/v1/workflows/?search=test')

        # Test workflow filtering
        self.make_request('GET', '/api/v1/workflows/?status=active&trigger_type=manual')

    def test_node_endpoints(self):
        """Test node management endpoints"""
        logger.info("🧩 Testing node endpoints...")

        # List node types
        result = self.make_request('GET', '/api/v1/nodes/types/')
        if result.success and result.response_data.get('results'):
            self.test_data['node_types'] = result.response_data['results']

        # Get node type details
        if self.test_data['node_types']:
            node_type = self.test_data['node_types'][0]
            node_type_id = node_type['id']

            self.make_request('GET', f'/api/v1/nodes/types/{node_type_id}/')

            # Test node type validation
            validation_data = {"config": {"timeout": 30}}
            self.make_request('POST', f'/api/v1/nodes/types/{node_type_id}/validate/', json=validation_data)

        # Test node categories
        self.make_request('GET', '/api/v1/nodes/categories/')

        # List credentials
        result = self.make_request('GET', '/api/v1/nodes/credentials/')
        if result.success and result.response_data.get('results'):
            self.test_data['credentials'] = result.response_data['results']

        # Create credential
        credential_data = {
            "name": f"Test Credential {uuid.uuid4().hex[:8]}",
            "credential_type": "api_key",
            "service_name": "test_service",
            "description": "Test credential for API testing",
            "credential_data": {"api_key": "test_key_123", "secret": "test_secret"}
        }

        result = self.make_request('POST', '/api/v1/nodes/credentials/', json=credential_data)
        if result.success:
            credential_id = result.response_data['id']

            # Get credential details
            self.make_request('GET', f'/api/v1/nodes/credentials/{credential_id}/')

            # Update credential
            update_data = {"description": "Updated credential description"}
            self.make_request('PATCH', f'/api/v1/nodes/credentials/{credential_id}/', json=update_data)

            # Test credential
            self.make_request('POST', f'/api/v1/nodes/credentials/{credential_id}/test/')

    def test_execution_endpoints(self):
        """Test execution management endpoints"""
        logger.info("⚡ Testing execution endpoints...")

        # List execution queue
        result = self.make_request('GET', '/api/v1/executions/queue/')

        # List execution history
        result = self.make_request('GET', '/api/v1/executions/history/')
        if result.success and result.response_data.get('results'):
            executions = result.response_data['results']

            if executions:
                execution_id = executions[0]['id']

                # Get execution details
                self.make_request('GET', f'/api/v1/executions/history/{execution_id}/')

                # Test execution retry (if failed)
                if executions[0].get('status') == 'failed':
                    self.make_request('POST', f'/api/v1/executions/queue/{execution_id}/retry/')

        # Test execution statistics
        self.make_request('GET', '/api/v1/executions/stats/')

        # List execution schedules
        self.make_request('GET', '/api/v1/executions/schedules/')

        # Create execution schedule
        if self.test_data['workflows']:
            workflow_id = self.test_data['workflows'][0]['id']
            schedule_data = {
                "workflow": workflow_id,
                "name": f"Test Schedule {uuid.uuid4().hex[:8]}",
                "cron_expression": "0 9 * * *",
                "timezone": "UTC",
                "is_active": True
            }

            result = self.make_request('POST', '/api/v1/executions/schedules/', json=schedule_data)
            if result.success:
                schedule_id = result.response_data['id']

                # Get schedule details
                self.make_request('GET', f'/api/v1/executions/schedules/{schedule_id}/')

                # Update schedule
                update_data = {"is_active": False}
                self.make_request('PATCH', f'/api/v1/executions/schedules/{schedule_id}/', json=update_data)

    def test_webhook_endpoints(self):
        """Test webhook endpoints"""
        logger.info("🔗 Testing webhook endpoints...")

        # List webhooks
        self.make_request('GET', '/api/v1/webhooks/')

        # Create webhook
        webhook_data = {
            "name": f"Test Webhook {uuid.uuid4().hex[:8]}",
            "url": f"https://api.example.com/webhook/{uuid.uuid4().hex[:8]}",
            "events": ["workflow.completed", "workflow.failed"],
            "is_active": True
        }

        result = self.make_request('POST', '/api/v1/webhooks/', json=webhook_data)
        if result.success:
            webhook_id = result.response_data['id']

            # Get webhook details
            self.make_request('GET', f'/api/v1/webhooks/{webhook_id}/')

            # Update webhook
            update_data = {"is_active": False}
            self.make_request('PATCH', f'/api/v1/webhooks/{webhook_id}/', json=update_data)

            # Test webhook
            self.make_request('POST', f'/api/v1/webhooks/{webhook_id}/test/')

            # Get webhook logs
            self.make_request('GET', f'/api/v1/webhooks/{webhook_id}/logs/')

    def test_analytics_endpoints(self):
        """Test analytics endpoints"""
        logger.info("📊 Testing analytics endpoints...")

        # List dashboards
        result = self.make_request('GET', '/api/v1/analytics/dashboards/')
        if result.success and result.response_data.get('results'):
            self.test_data['dashboards'] = result.response_data['results']

        # Create dashboard
        dashboard_data = {
            "name": f"Test Dashboard {uuid.uuid4().hex[:8]}",
            "description": "Test dashboard for API testing",
            "dashboard_type": "custom",
            "layout_config": {"grid": {"rows": 12, "cols": 12}}
        }

        result = self.make_request('POST', '/api/v1/analytics/dashboards/', json=dashboard_data)
        if result.success:
            dashboard_id = result.response_data['id']

            # Get dashboard details
            self.make_request('GET', f'/api/v1/analytics/dashboards/{dashboard_id}/')

            # Create widget
            widget_data = {
                "title": "Test Widget",
                "widget_type": "chart",
                "chart_type": "line",
                "query_config": {"metric": "executions", "timeframe": "7d"},
                "position_x": 0,
                "position_y": 0,
                "width": 6,
                "height": 4
            }

            result = self.make_request('POST', f'/api/v1/analytics/dashboards/{dashboard_id}/widgets/',
                                       json=widget_data)
            if result.success:
                widget_id = result.response_data['id']

                # Get widget data
                self.make_request('GET', f'/api/v1/analytics/widgets/{widget_id}/data/')

        # Test general analytics endpoints
        self.make_request('GET', '/api/v1/analytics/overview/')
        self.make_request('GET', '/api/v1/analytics/usage/')
        self.make_request('GET', '/api/v1/analytics/performance/')
        self.make_request('GET', '/api/v1/analytics/errors/')

        # Test metrics with filters
        self.make_request('GET', '/api/v1/analytics/metrics/?timeframe=7d&metric=executions')
        self.make_request('GET', '/api/v1/analytics/metrics/?timeframe=30d&metric=success_rate')

    def test_api_documentation(self):
        """Test API documentation endpoints"""
        logger.info("📚 Testing API documentation...")

        # Test OpenAPI schema
        self.make_request('GET', '/api/schema/')

        # Test Swagger UI
        self.make_request('GET', '/api/docs/')

        # Test ReDoc
        self.make_request('GET', '/api/redoc/')

    def test_error_scenarios(self):
        """Test error handling scenarios"""
        logger.info("🚫 Testing error scenarios...")

        # Test invalid endpoints
        self.make_request('GET', '/api/v1/invalid-endpoint/')

        # Test unauthorized access (remove auth header temporarily)
        original_auth = self.session.headers.get('Authorization')
        if original_auth:
            del self.session.headers['Authorization']
            self.make_request('GET', '/api/v1/workflows/')
            self.session.headers['Authorization'] = original_auth

        # Test invalid JSON
        self.make_request('POST', '/api/v1/workflows/', data="invalid json")

        # Test invalid IDs
        self.make_request('GET', f'/api/v1/workflows/{uuid.uuid4()}/')

        # Test malformed requests
        self.make_request('POST', '/api/v1/workflows/', json={"invalid": "data"})

    def test_pagination_and_filtering(self):
        """Test pagination and filtering capabilities"""
        logger.info("📄 Testing pagination and filtering...")

        # Test pagination
        self.make_request('GET', '/api/v1/workflows/?page=1&page_size=5')
        self.make_request('GET', '/api/v1/executions/history/?page=1&page_size=10')

        # Test filtering
        self.make_request('GET', '/api/v1/workflows/?status=active')
        self.make_request('GET', '/api/v1/workflows/?trigger_type=manual')
        self.make_request('GET', '/api/v1/executions/history/?status=completed')

        # Test search
        self.make_request('GET', '/api/v1/workflows/?search=test')

        # Test ordering
        self.make_request('GET', '/api/v1/workflows/?ordering=-created_at')
        self.make_request('GET', '/api/v1/workflows/?ordering=name')

    def run_performance_tests(self):
        """Run performance tests"""
        logger.info("🚀 Running performance tests...")

        endpoints = [
            '/api/v1/workflows/',
            '/api/v1/executions/history/',
            '/api/v1/analytics/overview/',
            '/api/v1/nodes/types/'
        ]

        for endpoint in endpoints:
            # Test multiple concurrent requests
            start_time = time.time()
            for _ in range(5):
                self.make_request('GET', endpoint)
            total_time = time.time() - start_time
            avg_time = total_time / 5
            logger.info(f"  {endpoint}: Average response time {avg_time:.3f}s")

    def run_all_tests(self):
        """Run comprehensive test suite"""
        logger.info("🧪 Starting comprehensive API test suite...")
        logger.info("=" * 60)

        start_time = time.time()

        # Check if server is accessible
        if not self.test_health_check():
            logger.error("❌ Server health check failed. Is the server running?")
            return False

        # Authenticate
        if not self.authenticate():
            logger.error("❌ Authentication failed. Cannot proceed with tests.")
            return False

        # Run test suites
        test_suites = [
            self.test_auth_endpoints,
            self.test_organization_endpoints,
            self.test_workflow_endpoints,
            self.test_node_endpoints,
            self.test_execution_endpoints,
            self.test_webhook_endpoints,
            self.test_analytics_endpoints,
            self.test_api_documentation,
            self.test_pagination_and_filtering,
            self.test_error_scenarios,
            self.run_performance_tests
        ]

        for test_suite in test_suites:
            try:
                test_suite()
            except Exception as e:
                logger.error(f"❌ Test suite {test_suite.__name__} failed: {e}")

        total_time = time.time() - start_time

        # Generate test report
        self.generate_report(total_time)

        return True

    def generate_report(self, total_time: float):
        """Generate comprehensive test report"""
        logger.info("=" * 60)
        logger.info("📋 TEST REPORT")
        logger.info("=" * 60)

        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - successful_tests

        avg_response_time = sum(r.response_time for r in self.test_results) / total_tests if total_tests > 0 else 0

        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Successful: {successful_tests} ({successful_tests / total_tests * 100:.1f}%)")
        logger.info(f"Failed: {failed_tests} ({failed_tests / total_tests * 100:.1f}%)")
        logger.info(f"Average Response Time: {avg_response_time:.3f}s")
        logger.info(f"Total Execution Time: {total_time:.2f}s")

        # Status code distribution
        status_codes = {}
        for result in self.test_results:
            status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1

        logger.info("\nStatus Code Distribution:")
        for code, count in sorted(status_codes.items()):
            logger.info(f"  {code}: {count}")

        # Failed tests details
        if failed_tests > 0:
            logger.info("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result.success:
                    logger.info(f"  {result.method} {result.endpoint} - {result.error_message}")

        # Performance metrics
        logger.info("\n⚡ Performance Metrics:")

        # Group by endpoint for better analysis
        endpoint_stats = {}
        for result in self.test_results:
            key = f"{result.method} {result.endpoint}"
            if key not in endpoint_stats:
                endpoint_stats[key] = []
            endpoint_stats[key].append(result.response_time)

        for endpoint, times in endpoint_stats.items():
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            if avg_time > 1.0:  # Only show slow endpoints
                logger.info(f"  {endpoint}: avg={avg_time:.3f}s, max={max_time:.3f}s, min={min_time:.3f}s")

        # Test data summary
        logger.info("\n📊 Test Data Created:")
        for key, items in self.test_data.items():
            if items:
                logger.info(f"  {key.title()}: {len(items)}")

        logger.info("=" * 60)

        if failed_tests == 0:
            logger.info("🎉 ALL TESTS PASSED!")
        else:
            logger.info(f"⚠️  {failed_tests} TESTS FAILED")

        logger.info("=" * 60)

    def save_results_to_file(self, filename: str = None):
        """Save test results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"api_test_results_{timestamp}.json"

        results_data = {
            'test_summary': {
                'total_tests': len(self.test_results),
                'successful_tests': sum(1 for r in self.test_results if r.success),
                'failed_tests': sum(1 for r in self.test_results if not r.success),
                'average_response_time': sum(r.response_time for r in self.test_results) / len(
                    self.test_results) if self.test_results else 0
            },
            'test_results': [
                {
                    'endpoint': r.endpoint,
                    'method': r.method,
                    'status_code': r.status_code,
                    'response_time': r.response_time,
                    'success': r.success,
                    'error_message': r.error_message
                }
                for r in self.test_results
            ],
            'test_data_created': {
                key: len(items) for key, items in self.test_data.items()
            }
        }

        with open(filename, 'w') as f:
            json.dump(results_data, f, indent=2)

        logger.info(f"💾 Test results saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description='Workflow Platform API Test Suite')
    parser.add_argument('--base-url', default='http://localhost:8000',
                        help='Base URL of the API server (default: http://localhost:8000)')
    parser.add_argument('--username', default='admin',
                        help='Username for authentication (default: admin)')
    parser.add_argument('--password', default='admin123',
                        help='Password for authentication (default: admin123)')
    parser.add_argument('--save-results', action='store_true',
                        help='Save test results to JSON file')
    parser.add_argument('--output-file',
                        help='Output file for test results (auto-generated if not specified)')

    args = parser.parse_args()

    # Create tester instance
    tester = WorkflowPlatformAPITester(base_url=args.base_url)

    # Run tests
    success = tester.run_all_tests()

    # Save results if requested
    if args.save_results:
        tester.save_results_to_file(args.output_file)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()