"""
Core Middleware - Custom middleware for the workflow platform
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from apps.organizations.models import OrganizationMember

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware for multi-tenant organization context
    """

    def process_request(self, request):
        """Set organization context based on user"""
        request.organization = None
        request.organization_member = None

        # Skip for anonymous users
        if isinstance(request.user, AnonymousUser) or not request.user.is_authenticated:
            return None

        try:
            # Get the user's active organization membership
            membership = OrganizationMember.objects.filter(
                user=request.user,
                status='active'
            ).select_related('organization').first()

            if membership:
                request.organization = membership.organization
                request.organization_member = membership

                # Set organization in thread-local storage for use in models
                from threading import local
                if not hasattr(local(), 'organization'):
                    local().organization = membership.organization

        except Exception as e:
            logger.error(f"Error setting organization context: {str(e)}")

        return None


class PerformanceMiddleware(MiddlewareMixin):
    """
    Middleware for performance monitoring and logging
    """

    def process_request(self, request):
        """Start timing the request"""
        request.start_time = time.time()
        return None

    def process_response(self, request, response):
        """Log request performance"""
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time

            # Log slow requests
            if duration > getattr(settings, 'SLOW_REQUEST_THRESHOLD', 2.0):
                logger.warning(
                    f"Slow request: {request.method} {request.path} "
                    f"took {duration:.2f}s - User: {getattr(request.user, 'username', 'anonymous')}"
                )

            # Add performance headers
            response['X-Response-Time'] = f"{duration:.3f}"

            # Store performance metrics for analytics
            if hasattr(request, 'organization') and request.organization:
                self._store_performance_metric(request, response, duration)

        return response

    def _store_performance_metric(self, request, response, duration):
        """Store performance metrics for analytics"""
        try:
            # Only store metrics for API endpoints
            if request.path.startswith('/api/'):
                from apps.analytics.models import AnalyticsMetric

                # Create performance metric
                AnalyticsMetric.objects.create(
                    organization=request.organization,
                    name='api_response_time',
                    metric_type='duration',
                    category='performance',
                    value=duration,
                    unit='seconds',
                    aggregation_period='hour',
                    period_start=timezone.now().replace(minute=0, second=0, microsecond=0),
                    period_end=timezone.now().replace(minute=59, second=59, microsecond=999999),
                    metadata={
                        'endpoint': request.path,
                        'method': request.method,
                        'status_code': response.status_code
                    }
                )
        except Exception as e:
            logger.error(f"Error storing performance metric: {str(e)}")


class RateLimitMiddleware(MiddlewareMixin):
    """
    Simple rate limiting middleware
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.cache = {}  # In production, use Redis
        super().__init__(get_response)

    def process_request(self, request):
        """Check rate limits"""
        # Skip rate limiting for non-API requests
        if not request.path.startswith('/api/'):
            return None

        # Get client identifier
        client_id = self._get_client_id(request)

        # Check rate limit
        if self._is_rate_limited(client_id, request):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.',
                'retry_after': 3600  # 1 hour
            }, status=429)

        return None

    def _get_client_id(self, request):
        """Get client identifier for rate limiting"""
        # Use API key if present
        api_key = request.META.get('HTTP_X_API_KEY')
        if api_key:
            return f"api_key:{api_key}"

        # Use user ID if authenticated
        if request.user.is_authenticated:
            return f"user:{request.user.id}"

        # Use IP address as fallback
        ip = self._get_client_ip(request)
        return f"ip:{ip}"

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _is_rate_limited(self, client_id, request):
        """Check if client is rate limited"""
        now = time.time()
        window = 3600  # 1 hour window

        # Get rate limit based on client type
        if client_id.startswith('api_key:'):
            limit = 10000  # 10k requests per hour for API keys
        elif client_id.startswith('user:'):
            limit = 1000   # 1k requests per hour for authenticated users
        else:
            limit = 100    # 100 requests per hour for anonymous users

        # Clean old entries
        cutoff = now - window
        if client_id in self.cache:
            self.cache[client_id] = [
                timestamp for timestamp in self.cache[client_id]
                if timestamp > cutoff
            ]
        else:
            self.cache[client_id] = []

        # Check if limit exceeded
        if len(self.cache[client_id]) >= limit:
            return True

        # Record this request
        self.cache[client_id].append(now)
        return False


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to responses
    """

    def process_response(self, request, response):
        """Add security headers"""
        # Content Security Policy
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' wss: ws:; "
            "frame-ancestors 'none';"
        )

        # Other security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # HSTS for HTTPS
        if request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response


class APIVersioningMiddleware(MiddlewareMixin):
    """
    Handle API versioning
    """

    def process_request(self, request):
        """Set API version context"""
        # Default version
        request.api_version = 'v1'

        # Check for version in header
        version_header = request.META.get('HTTP_API_VERSION')
        if version_header:
            request.api_version = version_header

        # Check for version in URL
        if request.path.startswith('/api/'):
            path_parts = request.path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[1].startswith('v'):
                request.api_version = path_parts[1]

        return None


class CORSMiddleware(MiddlewareMixin):
    """
    Handle CORS for API requests
    """

    def process_response(self, request, response):
        """Add CORS headers for API requests"""
        if request.path.startswith('/api/'):
            # Get allowed origins from settings
            allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', ['http://localhost:3000'])
            origin = request.META.get('HTTP_ORIGIN')

            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin

            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = (
                'Accept, Content-Type, Authorization, X-API-Key, API-Version'
            )
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '3600'

        return response

    def process_request(self, request):
        """Handle OPTIONS requests for CORS preflight"""
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            response = JsonResponse({})
            return self.process_response(request, response)

        return None


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Log API requests for audit and debugging
    """

    def process_request(self, request):
        """Log incoming requests"""
        # Only log API requests
        if not request.path.startswith('/api/'):
            return None

        # Skip health check endpoints
        if request.path in ['/api/health/', '/health/']:
            return None

        logger.info(
            f"API Request: {request.method} {request.path} "
            f"- User: {getattr(request.user, 'username', 'anonymous')} "
            f"- IP: {self._get_client_ip(request)} "
            f"- User-Agent: {request.META.get('HTTP_USER_AGENT', '')[:100]}"
        )

        return None

    def process_response(self, request, response):
        """Log response details for errors"""
        if (request.path.startswith('/api/') and
            response.status_code >= 400 and
            request.path not in ['/api/health/', '/health/']):

            logger.warning(
                f"API Error Response: {request.method} {request.path} "
                f"- Status: {response.status_code} "
                f"- User: {getattr(request.user, 'username', 'anonymous')}"
            )

        return response

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    Handle maintenance mode
    """

    def process_request(self, request):
        """Check if system is in maintenance mode"""
        # Check for maintenance mode setting
        maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)

        if maintenance_mode:
            # Allow access to admin and health endpoints
            allowed_paths = ['/admin/', '/health/', '/api/health/']

            if not any(request.path.startswith(path) for path in allowed_paths):
                # Allow superusers to access during maintenance
                if not (request.user.is_authenticated and request.user.is_superuser):
                    return JsonResponse({
                        'error': 'System Maintenance',
                        'message': 'The system is currently under maintenance. Please try again later.',
                        'maintenance': True
                    }, status=503)

        return None


class ErrorHandlingMiddleware:
    """Middleware to handle API errors gracefully"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            if request.path.startswith('/api/'):
                logger.error(f"API Error: {request.path} - {str(e)}")
                return JsonResponse({
                    'error': 'Internal server error',
                    'message': 'An unexpected error occurred',
                    'path': request.path
                }, status=500)
            raise