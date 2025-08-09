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


@api_view(['GET'])
@permission_classes([AllowAny])
@cache_page(60)  # Cache for 1 minute
def health_check(request):
    """
    Basic health check endpoint
    Returns 200 if the service is healthy
    """
    try:
        health_status = HealthChecker.get_system_health()

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