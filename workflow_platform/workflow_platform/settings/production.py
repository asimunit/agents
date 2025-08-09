"""
Production settings for Workflow Platform
"""
from .base import *
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

# Security settings
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '*']
env = environ.Env(
    DEBUG=(bool, False)
)
# Security headers
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Additional security headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Database configuration for production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT', default='5432'),
        'OPTIONS': {
            'MAX_CONNS': env.int('DATABASE_POOL_SIZE', default=20),
            'sslmode': 'require',
        },
        'CONN_MAX_AGE': 600,
    }
}

# Read replica (optional)
if env('DB_READ_HOST', default=None):
    DATABASES['read'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_READ_USER', default=env('DB_USER')),
        'PASSWORD': env('DB_READ_PASSWORD', default=env('DB_PASSWORD')),
        'HOST': env('DB_READ_HOST'),
        'PORT': env('DB_READ_PORT', default='5432'),
        'OPTIONS': {
            'MAX_CONNS': env.int('DATABASE_POOL_SIZE', default=20),
            'sslmode': 'require',
        },
        'CONN_MAX_AGE': 600,
    }

# Cache configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': env.int('REDIS_POOL_SIZE', default=50),
                'ssl_cert_reqs': None,
            },
        },
        'KEY_PREFIX': 'workflow_platform',
        'TIMEOUT': 300,
    }
}

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 hours

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# AWS S3 configuration for static/media files
if env('AWS_ACCESS_KEY_ID', default=None):
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = env('AWS_S3_CUSTOM_DOMAIN', default=None)
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }

    # Use S3 for static and media files
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.StaticS3Boto3Storage'

    if AWS_S3_CUSTOM_DOMAIN:
        STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    else:
        STATIC_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/static/'
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/media/'

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

# Celery configuration for production
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND')
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Production Celery settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes

# Sentry configuration for error tracking
SENTRY_DSN = env('SENTRY_DSN', default=None)
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style='url'),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment='production',
        release=env('APP_VERSION', default='latest'),
    )

# Logging configuration for production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"level": "{levelname}", "time": "{asctime}", "module": "{module}", "message": "{message}"}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/production.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/errors.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'workflow_engine': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# CORS settings for production
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# API rate limiting
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': env('API_RATE_LIMIT_ANON', default='100/hour'),
    'user': env('API_RATE_LIMIT_USER', default='1000/hour'),
    'burst': env('API_RATE_LIMIT_BURST', default='60/min'),
}

# Production-specific middleware
MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.TenantMiddleware',
    'apps.core.middleware.PerformanceMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
]

# Cache settings
CACHE_MIDDLEWARE_ALIAS = 'default'
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = 'workflow_platform'

# Production webhook settings
WEBHOOK_BASE_URL = env('WEBHOOK_BASE_URL')
WEBHOOK_TIMEOUT = env.int('WEBHOOK_TIMEOUT', default=30)
WEBHOOK_MAX_RETRIES = env.int('WEBHOOK_MAX_RETRIES', default=3)

# Production execution settings
WORKFLOW_EXECUTION_TIMEOUT = env.int('WORKFLOW_EXECUTION_TIMEOUT', default=300)
MAX_PARALLEL_EXECUTIONS = env.int('MAX_PARALLEL_EXECUTIONS', default=10)

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int('MAX_FILE_SIZE', default=10 * 1024 * 1024)  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int('MAX_FILE_SIZE', default=10 * 1024 * 1024)  # 10MB

# Performance settings
DATABASE_POOL_SIZE = env.int('DATABASE_POOL_SIZE', default=20)
REDIS_POOL_SIZE = env.int('REDIS_POOL_SIZE', default=50)

# Feature flags
ENABLE_ANALYTICS = env.bool('ENABLE_ANALYTICS', default=True)
ENABLE_WEBHOOKS = env.bool('ENABLE_WEBHOOKS', default=True)
ENABLE_MARKETPLACE = env.bool('ENABLE_MARKETPLACE', default=True)
ENABLE_AI_FEATURES = env.bool('ENABLE_AI_FEATURES', default=False)

# Monitoring settings
if env.bool('PROMETHEUS_METRICS_ENABLED', default=True):
    INSTALLED_APPS += ['django_prometheus']
    MIDDLEWARE = ['django_prometheus.middleware.PrometheusBeforeMiddleware'] + MIDDLEWARE
    MIDDLEWARE += ['django_prometheus.middleware.PrometheusAfterMiddleware']

# Health check settings
HEALTH_CHECK = {
    'DATABASE': True,
    'CACHE': True,
    'CELERY': True,
}

# Backup settings
BACKUP_ENABLED = env.bool('ENABLE_AUTO_BACKUP', default=False)
BACKUP_STORAGE_URL = env('BACKUP_STORAGE_URL', default=None)
BACKUP_RETENTION_DAYS = env.int('BACKUP_RETENTION_DAYS', default=30)

print("🚀 Production server configuration loaded")