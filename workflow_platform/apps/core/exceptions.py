"""
Core Exceptions for Workflow Platform
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class WorkflowPlatformError(Exception):
    """Base exception for all workflow platform errors"""

    def __init__(self, message, error_code=None, details=None):
        self.message = message
        self.error_code = error_code or 'WORKFLOW_PLATFORM_ERROR'
        self.details = details or {}
        super().__init__(self.message)


class WorkflowExecutionError(WorkflowPlatformError):
    """Raised when workflow execution fails"""

    def __init__(self, message, workflow_id=None, execution_id=None, node_id=None, **kwargs):
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.node_id = node_id
        super().__init__(message, error_code='WORKFLOW_EXECUTION_ERROR', **kwargs)


class NodeExecutionError(WorkflowPlatformError):
    """Raised when node execution fails"""

    def __init__(self, message, node_type=None, node_id=None, **kwargs):
        self.node_type = node_type
        self.node_id = node_id
        super().__init__(message, error_code='NODE_EXECUTION_ERROR', **kwargs)


class NodeConfigurationError(WorkflowPlatformError):
    """Raised when node configuration is invalid"""

    def __init__(self, message, node_type=None, config_field=None, **kwargs):
        self.node_type = node_type
        self.config_field = config_field
        super().__init__(message, error_code='NODE_CONFIGURATION_ERROR', **kwargs)


class WorkflowValidationError(WorkflowPlatformError):
    """Raised when workflow validation fails"""

    def __init__(self, message, workflow_id=None, validation_errors=None, **kwargs):
        self.workflow_id = workflow_id
        self.validation_errors = validation_errors or []
        super().__init__(message, error_code='WORKFLOW_VALIDATION_ERROR', **kwargs)


class WorkflowTimeoutError(WorkflowPlatformError):
    """Raised when workflow execution times out"""

    def __init__(self, message, timeout_seconds=None, **kwargs):
        self.timeout_seconds = timeout_seconds
        super().__init__(message, error_code='WORKFLOW_TIMEOUT_ERROR', **kwargs)


class CredentialError(WorkflowPlatformError):
    """Raised when credential operations fail"""

    def __init__(self, message, credential_type=None, credential_name=None, **kwargs):
        self.credential_type = credential_type
        self.credential_name = credential_name
        super().__init__(message, error_code='CREDENTIAL_ERROR', **kwargs)


class WebhookError(WorkflowPlatformError):
    """Raised when webhook operations fail"""

    def __init__(self, message, webhook_id=None, delivery_id=None, **kwargs):
        self.webhook_id = webhook_id
        self.delivery_id = delivery_id
        super().__init__(message, error_code='WEBHOOK_ERROR', **kwargs)


class OrganizationLimitError(WorkflowPlatformError):
    """Raised when organization limits are exceeded"""

    def __init__(self, message, limit_type=None, current_value=None, limit_value=None, **kwargs):
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value
        super().__init__(message, error_code='ORGANIZATION_LIMIT_ERROR', **kwargs)


class RateLimitError(WorkflowPlatformError):
    """Raised when rate limits are exceeded"""

    def __init__(self, message, rate_limit_type=None, reset_time=None, **kwargs):
        self.rate_limit_type = rate_limit_type
        self.reset_time = reset_time
        super().__init__(message, error_code='RATE_LIMIT_ERROR', **kwargs)


class AuthenticationError(WorkflowPlatformError):
    """Raised when authentication fails"""

    def __init__(self, message, auth_type=None, **kwargs):
        self.auth_type = auth_type
        super().__init__(message, error_code='AUTHENTICATION_ERROR', **kwargs)


class PermissionError(WorkflowPlatformError):
    """Raised when permission checks fail"""

    def __init__(self, message, required_permission=None, **kwargs):
        self.required_permission = required_permission
        super().__init__(message, error_code='PERMISSION_ERROR', **kwargs)


class APIError(WorkflowPlatformError):
    """Raised when external API calls fail"""

    def __init__(self, message, api_endpoint=None, status_code=None, response_data=None, **kwargs):
        self.api_endpoint = api_endpoint
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message, error_code='API_ERROR', **kwargs)


class DatabaseError(WorkflowPlatformError):
    """Raised when database operations fail"""

    def __init__(self, message, operation=None, table=None, **kwargs):
        self.operation = operation
        self.table = table
        super().__init__(message, error_code='DATABASE_ERROR', **kwargs)


class FileProcessingError(WorkflowPlatformError):
    """Raised when file processing fails"""

    def __init__(self, message, file_path=None, file_type=None, **kwargs):
        self.file_path = file_path
        self.file_type = file_type
        super().__init__(message, error_code='FILE_PROCESSING_ERROR', **kwargs)


class EncryptionError(WorkflowPlatformError):
    """Raised when encryption/decryption fails"""

    def __init__(self, message, operation=None, **kwargs):
        self.operation = operation  # 'encrypt' or 'decrypt'
        super().__init__(message, error_code='ENCRYPTION_ERROR', **kwargs)


class SchedulingError(WorkflowPlatformError):
    """Raised when workflow scheduling fails"""

    def __init__(self, message, cron_expression=None, **kwargs):
        self.cron_expression = cron_expression
        super().__init__(message, error_code='SCHEDULING_ERROR', **kwargs)


class AnalyticsError(WorkflowPlatformError):
    """Raised when analytics operations fail"""

    def __init__(self, message, metric_name=None, calculation_type=None, **kwargs):
        self.metric_name = metric_name
        self.calculation_type = calculation_type
        super().__init__(message, error_code='ANALYTICS_ERROR', **kwargs)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for API responses
    """

    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Standard DRF errors
        custom_response_data = {
            'error': True,
            'error_code': 'API_ERROR',
            'message': 'An error occurred',
            'details': response.data,
            'timestamp': timezone.now().isoformat()
        }

        # Extract error message from DRF response
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                custom_response_data['message'] = response.data['detail']
            elif 'non_field_errors' in response.data:
                custom_response_data['message'] = response.data['non_field_errors'][0]
            elif len(response.data) == 1:
                field, errors = list(response.data.items())[0]
                if isinstance(errors, list) and errors:
                    custom_response_data['message'] = f"{field}: {errors[0]}"

        response.data = custom_response_data

    elif isinstance(exc, WorkflowPlatformError):
        # Handle custom workflow platform errors
        custom_response_data = {
            'error': True,
            'error_code': exc.error_code,
            'message': exc.message,
            'details': exc.details,
            'timestamp': timezone.now().isoformat()
        }

        # Add specific error attributes
        if hasattr(exc, 'workflow_id') and exc.workflow_id:
            custom_response_data['workflow_id'] = exc.workflow_id

        if hasattr(exc, 'node_id') and exc.node_id:
            custom_response_data['node_id'] = exc.node_id

        if hasattr(exc, 'execution_id') and exc.execution_id:
            custom_response_data['execution_id'] = exc.execution_id

        # Determine HTTP status code based on error type
        if isinstance(exc, (AuthenticationError, PermissionError)):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, (WorkflowValidationError, NodeConfigurationError)):
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, OrganizationLimitError):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif isinstance(exc, RateLimitError):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif isinstance(exc, WorkflowTimeoutError):
            status_code = status.HTTP_408_REQUEST_TIMEOUT
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        response = Response(custom_response_data, status=status_code)

    else:
        # Handle unexpected errors
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

        custom_response_data = {
            'error': True,
            'error_code': 'INTERNAL_SERVER_ERROR',
            'message': 'An unexpected error occurred',
            'details': {},
            'timestamp': timezone.now().isoformat()
        }

        # Don't expose internal error details in production
        from django.conf import settings
        if settings.DEBUG:
            custom_response_data['details'] = {
                'exception_type': type(exc).__name__,
                'exception_message': str(exc)
            }

        response = Response(custom_response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response


# Error views for HTTP errors
def custom_400_view(request, exception=None):
    """Custom 400 Bad Request view"""
    from django.http import JsonResponse

    return JsonResponse({
        'error': True,
        'error_code': 'BAD_REQUEST',
        'message': 'Bad Request',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=400)


def custom_403_view(request, exception=None):
    """Custom 403 Forbidden view"""
    from django.http import JsonResponse

    return JsonResponse({
        'error': True,
        'error_code': 'FORBIDDEN',
        'message': 'Access Forbidden',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=403)


def custom_404_view(request, exception=None):
    """Custom 404 Not Found view"""
    from django.http import JsonResponse

    return JsonResponse({
        'error': True,
        'error_code': 'NOT_FOUND',
        'message': 'Resource Not Found',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=404)


def custom_500_view(request):
    """Custom 500 Internal Server Error view"""
    from django.http import JsonResponse

    return JsonResponse({
        'error': True,
        'error_code': 'INTERNAL_SERVER_ERROR',
        'message': 'Internal Server Error',
        'details': {},
        'timestamp': timezone.now().isoformat()
    }, status=500)


# Context processors for error handling
class ErrorTrackingMiddleware:
    """Middleware to track and log errors"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Log API errors for monitoring
        if hasattr(response, 'status_code') and response.status_code >= 400:
            logger.warning(
                f"API Error: {response.status_code} {request.method} {request.path}",
                extra={
                    'status_code': response.status_code,
                    'method': request.method,
                    'path': request.path,
                    'user_id': request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                }
            )

        return response

    def process_exception(self, request, exception):
        """Process unhandled exceptions"""
        logger.error(
            f"Unhandled exception: {str(exception)}",
            exc_info=True,
            extra={
                'method': request.method,
                'path': request.path,
                'user_id': request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
                'ip_address': self._get_client_ip(request),
                'exception_type': type(exception).__name__,
            }
        )

        # Track error for analytics
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                from apps.analytics.models import ErrorAnalytics

                organization = request.user.organization_memberships.first().organization

                ErrorAnalytics.objects.create(
                    organization=organization,
                    error_type='system_error',
                    error_message=str(exception),
                    severity='high',
                    context_data={
                        'method': request.method,
                        'path': request.path,
                        'user_id': request.user.id,
                        'exception_type': type(exception).__name__,
                    }
                )
            except Exception:
                # Don't let error tracking cause more errors
                pass

        return None

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Validation helpers
def validate_workflow_limits(organization, operation_type='create'):
    """Validate workflow limits for organization"""

    if operation_type == 'create':
        current_workflows = organization.workflows.filter(is_latest_version=True).count()
        if organization.max_workflows > 0 and current_workflows >= organization.max_workflows:
            raise OrganizationLimitError(
                f"Workflow limit exceeded. Current: {current_workflows}, Limit: {organization.max_workflows}",
                limit_type='workflows',
                current_value=current_workflows,
                limit_value=organization.max_workflows
            )


def validate_execution_limits(organization):
    """Validate execution limits for organization"""

    from django.utils import timezone
    from datetime import timedelta

    # Check monthly execution limit
    if organization.max_executions_per_month > 0:
        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_executions = organization.workflows.filter(
            executions__started_at__gte=start_of_month
        ).count()

        if monthly_executions >= organization.max_executions_per_month:
            raise OrganizationLimitError(
                f"Monthly execution limit exceeded. Current: {monthly_executions}, Limit: {organization.max_executions_per_month}",
                limit_type='monthly_executions',
                current_value=monthly_executions,
                limit_value=organization.max_executions_per_month
            )


def validate_api_rate_limits(organization, request):
    """Validate API rate limits"""

    from django.core.cache import cache
    from django.utils import timezone

    # Use organization-specific rate limiting
    cache_key = f"api_rate_limit:{organization.id}"
    current_count = cache.get(cache_key, 0)

    if current_count >= organization.max_api_calls_per_hour:
        raise RateLimitError(
            f"API rate limit exceeded. Limit: {organization.max_api_calls_per_hour} calls per hour",
            rate_limit_type='api_calls',
            reset_time=timezone.now() + timedelta(hours=1)
        )

    # Increment counter
    cache.set(cache_key, current_count + 1, timeout=3600)  # 1 hour timeout