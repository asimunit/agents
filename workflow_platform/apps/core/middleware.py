"""
Custom Middleware for Workflow Platform
"""
import time
import logging
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
from apps.organizations.models import OrganizationMember

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Multi-tenant middleware that sets the current organization context
    """

    def process_request(self, request):
        """
        Set organization context based on user authentication
        """
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # Get user's active organization membership
                membership = request.user.organization_memberships.filter(status='active').first()
                if membership:
                    request.organization = membership.organization
                    request.user_role = membership.role
                    request.user_permissions = membership.permissions
                else:
                    request.organization = None
                    request.user_role = None
                    request.user_permissions = {}
            except Exception as e:
                logger.warning(f"Error setting tenant context: {str(e)}")
                request.organization = None
                request.user_role = None
                request.user_permissions = {}
        else:
            request.organization = None
            request.user_role = None
            request.user_permissions = {}

        return None

    def process_response(self, request, response):
        """
        Add organization context to response headers (for debugging)
        """
        if settings.DEBUG and hasattr(request, 'organization') and request.organization:
            response['X-Organization-ID'] = str(request.organization.id)
            response['X-Organization-Name'] = request.organization.name
            response['X-User-Role'] = getattr(request, 'user_role', 'unknown')

        return response


class PerformanceMiddleware(MiddlewareMixin):
    """
    Performance monitoring middleware
    """

    def process_request(self, request):
        """
        Start performance timing
        """
        request.start_time = time.time()
        request.db_queries_start = len(getattr(request, '_db_queries', []))

    def process_response(self, request, response):
        """
        Add performance headers and logging
        """
        if hasattr(request, 'start_time'):
            # Calculate response time
            response_time = (time.time() - request.start_time) * 1000  # milliseconds

            # Add performance headers
            response['X-Response-Time'] = f"{response_time:.2f}ms"

            # Log slow requests
            if response_time > getattr(settings, 'SLOW_REQUEST_THRESHOLD', 1000):
                logger.warning(
                    f"Slow request: {request.method} {request.path} took {response_time:.2f}ms",
                    extra={
                        'request_method': request.method,
                        'request_path': request.path,
                        'response_time_ms': response_time,
                        'status_code': response.status_code,
                        'user_id': request.user.id if hasattr(request,
                                                              'user') and request.user.is_authenticated else None,
                    }
                )

            # Add database query count (in debug mode)
            if settings.DEBUG:
                from django.db import connection
                response['X-DB-Queries'] = len(connection.queries)

        return response


class RateLimitMiddleware(MiddlewareMixin):
    """
    API rate limiting middleware
    """

    def process_request(self, request):
        """
        Check rate limits for API requests
        """
        # Only apply to API endpoints
        if not request.path.startswith('/api/'):
            return None

        # Get client identifier
        client_id = self._get_client_identifier(request)

        # Determine rate limits based on authentication
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Authenticated user limits
            if hasattr(request, 'organization') and request.organization:
                rate_limit = request.organization.max_api_calls_per_hour
                window = 3600  # 1 hour
            else:
                rate_limit = getattr(settings, 'API_RATE_LIMIT_USER', 1000)
                window = 3600
        else:
            # Anonymous user limits
            rate_limit = getattr(settings, 'API_RATE_LIMIT_ANON', 100)
            window = 3600

        # Check rate limit
        cache_key = f"rate_limit:{client_id}"
        current_requests = cache.get(cache_key, 0)

        if current_requests >= rate_limit:
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'limit': rate_limit,
                'window_seconds': window,
                'retry_after': window
            }, status=429)

        # Increment counter
        cache.set(cache_key, current_requests + 1, timeout=window)

        return None

    def _get_client_identifier(self, request):
        """
        Get unique client identifier for rate limiting
        """
        # Use user ID if authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            return f"user:{request.user.id}"

        # Use IP address for anonymous users
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        return f"ip:{ip}"


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to responses
    """

    def process_response(self, request, response):
        """
        Add security headers
        """
        # Content Security Policy
        if not response.get('Content-Security-Policy'):
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https: wss:; "
                "frame-ancestors 'none';"
            )

        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # HSTS (only in production with HTTPS)
        if not settings.DEBUG and request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

        return response


class APIVersionMiddleware(MiddlewareMixin):
    """
    API versioning middleware
    """

    def process_request(self, request):
        """
        Extract and validate API version
        """
        if request.path.startswith('/api/'):
            # Extract version from URL path
            path_parts = request.path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[1].startswith('v'):
                version = path_parts[1]
            else:
                # Default to v1 if no version specified
                version = 'v1'

            # Validate version
            supported_versions = getattr(settings, 'API_SUPPORTED_VERSIONS', ['v1'])
            if version not in supported_versions:
                return JsonResponse({
                    'error': 'Unsupported API version',
                    'supported_versions': supported_versions
                }, status=400)

            request.api_version = version

        return None

    def process_response(self, request, response):
        """
        Add API version to response headers
        """
        if hasattr(request, 'api_version'):
            response['X-API-Version'] = request.api_version

        return response


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Request logging middleware for audit trails
    """

    def process_request(self, request):
        """
        Log incoming requests
        """
        # Only log API requests and sensitive operations
        if (request.path.startswith('/api/') or
                request.method in ['POST', 'PUT', 'PATCH', 'DELETE']):
            logger.info(
                f"Request: {request.method} {request.path}",
                extra={
                    'request_method': request.method,
                    'request_path': request.path,
                    'user_id': request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
                    'organization_id': str(request.organization.id) if hasattr(request,
                                                                               'organization') and request.organization else None,
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'content_type': request.content_type,
                }
            )

        return None

    def process_response(self, request, response):
        """
        Log response details
        """
        # Log errors and important operations
        if (response.status_code >= 400 or
                (hasattr(request, 'path') and request.path.startswith('/api/') and
                 request.method in ['POST', 'PUT', 'PATCH', 'DELETE'])):
            logger.info(
                f"Response: {response.status_code} for {request.method} {request.path}",
                extra={
                    'status_code': response.status_code,
                    'request_method': request.method,
                    'request_path': request.path,
                    'response_time_ms': getattr(request, 'response_time_ms', None),
                    'user_id': request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
                }
            )

        return response

    def _get_client_ip(self, request):
        """
        Get client IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class HealthCheckMiddleware(MiddlewareMixin):
    """
    Health check middleware for load balancers
    """

    def process_request(self, request):
        """
        Handle health check requests
        """
        if request.path in ['/health/', '/health', '/healthz', '/ping']:
            return JsonResponse({
                'status': 'healthy',
                'timestamp': timezone.now().isoformat(),
                'version': getattr(settings, 'APP_VERSION', '1.0.0')
            })

        return None


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    Maintenance mode middleware
    """

    def process_request(self, request):
        """
        Check if system is in maintenance mode
        """
        # Check maintenance mode flag
        maintenance_mode = cache.get('maintenance_mode', False)

        if maintenance_mode:
            # Allow access to admin and health endpoints
            allowed_paths = ['/admin/', '/health/', '/api/v1/auth/login/']
            if not any(request.path.startswith(path) for path in allowed_paths):

                # Allow superusers
                if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_superuser:
                    return None

                return JsonResponse({
                    'error': 'System is currently under maintenance',
                    'message': 'Please try again later',
                    'retry_after': 3600  # 1 hour
                }, status=503)

        return None


class CORSMiddleware(MiddlewareMixin):
    """
    Custom CORS middleware for fine-grained control
    """

    def process_response(self, request, response):
        """
        Add CORS headers
        """
        # Get allowed origins from settings
        allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        origin = request.META.get('HTTP_ORIGIN')

        if origin in allowed_origins or settings.DEBUG:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = (
                'Accept, Accept-Language, Content-Language, Content-Type, '
                'Authorization, X-Requested-With, X-API-Key'
            )
            response['Access-Control-Max-Age'] = '86400'  # 24 hours

        return response