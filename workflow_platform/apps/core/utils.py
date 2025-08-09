"""
Core Utilities for Workflow Platform
"""
import hashlib
import hmac
import json
import secrets
import base64
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Handles encryption and decryption of sensitive data"""

    def __init__(self):
        self.key = self._get_encryption_key()
        self.fernet = Fernet(self.key)

    def _get_encryption_key(self):
        """Get or generate encryption key"""
        secret_key = getattr(settings, 'ENCRYPTION_SECRET_KEY', settings.SECRET_KEY)

        # Derive key from secret
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'workflow_platform_salt',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        return key

    def encrypt(self, data: Union[str, Dict]) -> str:
        """Encrypt data"""
        try:
            if isinstance(data, dict):
                data = json.dumps(data)

            encrypted_data = self.fernet.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            raise

    def decrypt(self, encrypted_data: str) -> Union[str, Dict]:
        """Decrypt data"""
        try:
            decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.fernet.decrypt(decoded_data)

            # Try to parse as JSON, otherwise return as string
            try:
                return json.loads(decrypted_data.decode())
            except json.JSONDecodeError:
                return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            raise


# Global encryption manager instance
encryption_manager = EncryptionManager()


def encrypt_data(data: Union[str, Dict]) -> Tuple[str, str]:
    """Encrypt data and return encrypted data with key ID"""
    encrypted_data = encryption_manager.encrypt(data)
    key_id = generate_uuid()  # Generate unique key ID for tracking
    return encrypted_data, key_id


def decrypt_data(encrypted_data: str, key_id: str) -> Union[str, Dict]:
    """Decrypt data using key ID"""
    return encryption_manager.decrypt(encrypted_data)


def generate_uuid() -> str:
    """Generate a UUID string"""
    import uuid
    return str(uuid.uuid4())


def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token"""
    return secrets.token_urlsafe(length)


def generate_api_key() -> str:
    """Generate an API key with prefix"""
    return f"wp_{secrets.token_urlsafe(32)}"


def hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    """Hash password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return password_hash.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify password against hash"""
    computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return computed_hash.hex() == password_hash


def generate_webhook_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC signature for webhook"""
    signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook HMAC signature"""
    expected_signature = generate_webhook_signature(payload, secret)
    return hmac.compare_digest(expected_signature, signature)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    import re

    # Remove or replace unsafe characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:251 - len(ext)] + '.' + ext if ext else name[:255]

    return filename


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_bytes(bytes_count: int) -> str:
    """Format bytes in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"


def parse_cron_expression(cron_expr: str) -> Dict[str, Any]:
    """Parse cron expression and return components"""
    try:
        from croniter import croniter

        # Validate cron expression
        croniter(cron_expr)

        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression format")

        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'weekday': parts[4],
            'is_valid': True
        }
    except Exception as e:
        return {
            'is_valid': False,
            'error': str(e)
        }


def get_next_cron_run(cron_expr: str, base_time: datetime = None) -> Optional[datetime]:
    """Get next run time for cron expression"""
    try:
        from croniter import croniter

        base_time = base_time or timezone.now()
        cron = croniter(cron_expr, base_time)
        return cron.get_next(datetime)
    except Exception:
        return None


def calculate_execution_cost(execution_time_ms: float, compute_tier: str = 'standard') -> float:
    """Calculate execution cost based on time and tier"""

    # Example pricing tiers (per second)
    pricing = {
        'standard': 0.0001,  # $0.0001 per second
        'premium': 0.0002,  # $0.0002 per second
        'enterprise': 0.0005  # $0.0005 per second
    }

    rate = pricing.get(compute_tier, pricing['standard'])
    execution_time_seconds = execution_time_ms / 1000

    return execution_time_seconds * rate


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate data against JSON schema"""
    try:
        import jsonschema

        jsonschema.validate(data, schema)
        return True, []
    except jsonschema.ValidationError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Schema validation error: {str(e)}"]


def extract_json_path(data: Dict[str, Any], json_path: str) -> Any:
    """Extract value using JSONPath expression"""
    try:
        import jsonpath_ng

        expr = jsonpath_ng.parse(json_path)
        matches = [match.value for match in expr.find(data)]

        if len(matches) == 0:
            return None
        elif len(matches) == 1:
            return matches[0]
        else:
            return matches
    except Exception:
        return None


def deep_merge_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """Deep merge two dictionaries"""
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(data: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """Flatten nested dictionary"""
    items = []

    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key

        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))

    return dict(items)


def get_client_ip(request) -> str:
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request) -> str:
    """Get user agent from request"""
    return request.META.get('HTTP_USER_AGENT', '')


def is_valid_email(email: str) -> bool:
    """Validate email address"""
    import re

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def is_valid_url(url: str) -> bool:
    """Validate URL"""
    try:
        from django.core.validators import URLValidator

        validator = URLValidator()
        validator(url)
        return True
    except Exception:
        return False


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncate string to maximum length"""
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Split list into chunks of specified size"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def retry_operation(func, max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry operation with exponential backoff"""
    import time

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e

            time.sleep(delay * (backoff ** attempt))


class RateLimiter:
    """Simple rate limiter using cache"""

    def __init__(self, key_prefix: str = 'rate_limit'):
        self.key_prefix = key_prefix

    def is_allowed(self, identifier: str, limit: int, window: int) -> Tuple[bool, int]:
        """Check if request is allowed within rate limit"""
        cache_key = f"{self.key_prefix}:{identifier}"

        current_count = cache.get(cache_key, 0)

        if current_count >= limit:
            return False, current_count

        # Increment counter
        cache.set(cache_key, current_count + 1, timeout=window)

        return True, current_count + 1

    def reset(self, identifier: str):
        """Reset rate limit for identifier"""
        cache_key = f"{self.key_prefix}:{identifier}"
        cache.delete(cache_key)


class CircuitBreaker:
    """Circuit breaker pattern implementation"""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half-open

    def call(self, func, *args, **kwargs):
        """Call function with circuit breaker protection"""
        if self.state == 'open':
            if self._should_attempt_reset():
                self.state = 'half-open'
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset"""
        if self.last_failure_time is None:
            return True

        return (timezone.now() - self.last_failure_time).total_seconds() > self.timeout

    def _on_success(self):
        """Handle successful operation"""
        self.failure_count = 0
        self.state = 'closed'

    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = timezone.now()

        if self.failure_count >= self.failure_threshold:
            self.state = 'open'


def cache_result(cache_key: str, timeout: int = 300):
    """Decorator to cache function results"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Calculate and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)

            return result

        return wrapper

    return decorator


def batch_process(items: List, batch_size: int = 100, processor_func=None):
    """Process items in batches"""
    results = []

    for batch in chunk_list(items, batch_size):
        if processor_func:
            batch_result = processor_func(batch)
            results.extend(batch_result if isinstance(batch_result, list) else [batch_result])
        else:
            results.extend(batch)

    return results


def measure_execution_time(func):
    """Decorator to measure function execution time"""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = (time.time() - start_time) * 1000  # milliseconds

        logger.debug(f"Function {func.__name__} executed in {execution_time:.2f}ms")

        return result

    return wrapper


class HealthChecker:
    """Health check utilities"""

    @staticmethod
    def check_database():
        """Check database connectivity"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True, "Database connection successful"
        except Exception as e:
            return False, f"Database connection failed: {str(e)}"

    @staticmethod
    def check_redis():
        """Check Redis connectivity"""
        try:
            from django.core.cache import cache
            cache.set('health_check', 'ok', timeout=10)
            result = cache.get('health_check')

            if result == 'ok':
                return True, "Redis connection successful"
            else:
                return False, "Redis connection failed"
        except Exception as e:
            return False, f"Redis connection failed: {str(e)}"

    @staticmethod
    def check_celery():
        """Check Celery worker connectivity"""
        try:
            from celery import current_app

            # Send a simple task to check worker connectivity
            result = current_app.send_task('celery.ping', timeout=5)
            result.get(timeout=5)

            return True, "Celery workers responding"
        except Exception as e:
            return False, f"Celery workers not responding: {str(e)}"

    @classmethod
    def get_system_health(cls):
        """Get overall system health status"""
        checks = {
            'database': cls.check_database(),
            'redis': cls.check_redis(),
            'celery': cls.check_celery(),
        }

        overall_status = all(check[0] for check in checks.values())

        return {
            'status': 'healthy' if overall_status else 'unhealthy',
            'checks': {
                name: {
                    'status': 'pass' if result[0] else 'fail',
                    'message': result[1]
                }
                for name, result in checks.items()
            },
            'timestamp': timezone.now().isoformat()
        }


def get_workflow_complexity_score(workflow_data: Dict) -> int:
    """Calculate workflow complexity score"""
    score = 0

    nodes = workflow_data.get('nodes', [])
    connections = workflow_data.get('connections', [])

    # Base score from node count
    score += len(nodes) * 2

    # Add score for connections
    score += len(connections)

    # Add score for complex node types
    complex_node_types = ['condition', 'loop', 'transform']
    for node in nodes:
        if node.get('type') in complex_node_types:
            score += 5

    # Add score for nested workflows
    for node in nodes:
        if node.get('type') == 'subworkflow':
            score += 10

    return min(score, 100)  # Cap at 100


def optimize_workflow_performance(workflow_data: Dict) -> Dict:
    """Suggest performance optimizations for workflow"""
    suggestions = []

    nodes = workflow_data.get('nodes', [])
    connections = workflow_data.get('connections', [])

    # Check for sequential HTTP requests that could be parallelized
    http_nodes = [node for node in nodes if node.get('type') == 'http_request']
    if len(http_nodes) > 3:
        suggestions.append({
            'type': 'parallelization',
            'message': 'Consider parallelizing HTTP requests to improve performance',
            'affected_nodes': [node['id'] for node in http_nodes]
        })

    # Check for unnecessary data transformations
    transform_nodes = [node for node in nodes if node.get('type') in ['json', 'transform']]
    if len(transform_nodes) > 5:
        suggestions.append({
            'type': 'optimization',
            'message': 'Multiple data transformations detected. Consider combining them.',
            'affected_nodes': [node['id'] for node in transform_nodes]
        })

    # Check for potential timeout issues
    for node in nodes:
        if node.get('configuration', {}).get('timeout', 30) > 120:
            suggestions.append({
                'type': 'timeout',
                'message': f'Node {node.get("name", node["id"])} has high timeout value',
                'affected_nodes': [node['id']]
            })

    return {
        'suggestions': suggestions,
        'complexity_score': get_workflow_complexity_score(workflow_data)
    }