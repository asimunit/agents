"""
Core Views - Health checks and system status
"""
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.conf import settings
import json

from .utils import HealthChecker


# Create or replace: apps/core/views.py health_check function

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint that always returns 200
    """
    return Response({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'service': 'workflow-platform',
        'version': '1.0.0'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def detailed_health_check(request):
    """
    Detailed health check with service dependencies
    """
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'checks': {}
        }

        # Check database
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_status['checks']['database'] = {'status': 'healthy', 'message': 'Connected'}
        except Exception as e:
            health_status['checks']['database'] = {'status': 'unhealthy', 'message': str(e)}
            health_status['status'] = 'unhealthy'

        # Check cache/Redis (optional)
        try:
            from django.core.cache import cache
            cache.set('health_check', 'ok', timeout=10)
            result = cache.get('health_check')
            if result == 'ok':
                health_status['checks']['cache'] = {'status': 'healthy', 'message': 'Connected'}
            else:
                health_status['checks']['cache'] = {'status': 'unhealthy', 'message': 'Cache test failed'}
        except Exception as e:
            health_status['checks']['cache'] = {'status': 'unhealthy', 'message': str(e)}
            # Don't mark overall status as unhealthy for cache issues

        # Check Celery (optional)
        try:
            from celery import current_app
            from celery.exceptions import TimeoutError as CeleryTimeoutError

            # Quick ping to see if workers are available
            inspect = current_app.control.inspect()
            stats = inspect.stats()

            if stats:
                health_status['checks']['celery'] = {'status': 'healthy', 'message': f'{len(stats)} workers available'}
            else:
                health_status['checks']['celery'] = {'status': 'unhealthy', 'message': 'No workers available'}
        except Exception as e:
            health_status['checks']['celery'] = {'status': 'unhealthy', 'message': str(e)}
            # Don't mark overall status as unhealthy for Celery issues

        # Determine overall status code
        if health_status['status'] == 'healthy':
            status_code = status.HTTP_200_OK
        else:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(health_status, status=status_code)

    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
@permission_classes([AllowAny])
def system_status(request):
    """
    Detailed system status endpoint
    """
    try:
        from apps.workflows.models import Workflow, WorkflowExecution
        from apps.organizations.models import Organization
        from django.contrib.auth.models import User

        # Get basic statistics
        stats = {
            'timestamp': timezone.now().isoformat(),
            'version': getattr(settings, 'APP_VERSION', '1.0.0'),
            'environment': getattr(settings, 'ENVIRONMENT', 'production'),
            'counts': {
                'organizations': Organization.objects.count(),
                'users': User.objects.count(),
                'workflows': Workflow.objects.count(),
                'executions_today': WorkflowExecution.objects.filter(
                    started_at__date=timezone.now().date()
                ).count(),
            },
            'system': HealthChecker.get_system_health(),
        }

        return Response(stats)

    except Exception as e:
        return Response({
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@require_http_methods(["GET"])
def metrics(request):
    """
    Prometheus metrics endpoint
    """
    try:
        from django_prometheus.exports import ExportToDjangoView
        return ExportToDjangoView(request)
    except ImportError:
        return HttpResponse("Prometheus metrics not available", status=404)


# Error handler views
def custom_400_view(request, exception=None):
    """Custom 400 Bad Request view"""
    return JsonResponse({
        'error': True,
        'error_code': 'BAD_REQUEST',
        'message': 'Bad Request',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=400)


def custom_403_view(request, exception=None):
    """Custom 403 Forbidden view"""
    return JsonResponse({
        'error': True,
        'error_code': 'FORBIDDEN',
        'message': 'Access Forbidden',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=403)


def custom_404_view(request, exception=None):
    """Custom 404 Not Found view"""
    return JsonResponse({
        'error': True,
        'error_code': 'NOT_FOUND',
        'message': 'Resource Not Found',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=404)


def custom_500_view(request):
    """Custom 500 Internal Server Error view"""
    return JsonResponse({
        'error': True,
        'error_code': 'INTERNAL_SERVER_ERROR',
        'message': 'Internal Server Error',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_info(request):
    """
    API information endpoint
    """
    return Response({
        'name': 'Workflow Platform API',
        'version': 'v1',
        'description': 'Enterprise workflow automation platform',
        'documentation': '/api/docs/',
        'endpoints': {
            'authentication': '/api/v1/auth/',
            'workflows': '/api/v1/workflows/',
            'executions': '/api/v1/executions/',
            'nodes': '/api/v1/nodes/',
            'webhooks': '/api/v1/webhooks/',
            'analytics': '/api/v1/analytics/',
            'organizations': '/api/v1/organizations/',
        },
        'features': [
            'Multi-tenant architecture',
            'Visual workflow builder',
            'Real-time execution monitoring',
            'Advanced analytics',
            'Webhook management',
            'Custom node development',
            'Enterprise authentication',
        ]
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_test(request):
    """
    Test webhook endpoint for development
    """
    return Response({
        'received': True,
        'timestamp': timezone.now().isoformat(),
        'method': request.method,
        'headers': dict(request.headers),
        'data': request.data,
    })


# Add this to apps/core/views.py (replace the existing health_check function)

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint for development
    Returns 200 if the basic service is healthy
    """
    try:
        # Just check database connectivity for now
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Basic health response
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'database': 'connected',
            'django': 'running',
            'environment': getattr(settings, 'DEBUG', False) and 'development' or 'production'
        }

        return Response(health_status, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)