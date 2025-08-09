"""
Celery Configuration for Workflow Platform
"""
import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'workflow_platform.settings.development')

app = Celery('workflow_platform')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule for periodic tasks
app.conf.beat_schedule = {
    'schedule-workflow-executions': {
        'task': 'apps.core.tasks.schedule_workflow_executions',
        'schedule': 60.0,  # Every minute
    },
    'cleanup-old-executions': {
        'task': 'apps.core.tasks.cleanup_old_executions',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'calculate-usage-statistics': {
        'task': 'apps.core.tasks.calculate_usage_statistics',
        'schedule': crontab(hour=1, minute=0),  # Daily at 1 AM
    },
    'capture-performance-snapshot': {
        'task': 'apps.core.tasks.capture_performance_snapshot',
        'schedule': 300.0,  # Every 5 minutes
    },
    'evaluate-alert-rules': {
        'task': 'apps.core.tasks.evaluate_alert_rules',
        'schedule': 60.0,  # Every minute
    },
    'generate-scheduled-reports': {
        'task': 'apps.core.tasks.generate_scheduled_reports',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
    'calculate-metric-values': {
        'task': 'apps.core.tasks.calculate_all_metrics',
        'schedule': 3600.0,  # Every hour
    },
}

# Celery configuration
app.conf.update(
    # Task routing
    task_routes={
        'apps.core.tasks.execute_workflow_task': {'queue': 'workflows'},
        'apps.core.tasks.schedule_workflow_executions': {'queue': 'scheduler'},
        'apps.core.tasks.calculate_usage_statistics': {'queue': 'analytics'},
        'apps.core.tasks.capture_performance_snapshot': {'queue': 'monitoring'},
        'apps.core.tasks.evaluate_alert_rules': {'queue': 'alerts'},
    },

    # Task configuration
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,

    # Result backend configuration
    result_expires=3600,  # 1 hour
    result_compression='gzip',

    # Task execution configuration
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes

    # Beat configuration
    beat_schedule_filename='celerybeat-schedule',

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)


# Custom task base class
class BaseTask(app.Task):
    """Base task class with error handling and monitoring"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Task failure handler"""
        import logging
        logger = logging.getLogger(__name__)

        logger.error(
            f"Task {self.name} failed: {exc}",
            extra={
                'task_id': task_id,
                'task_name': self.name,
                'args': args,
                'kwargs': kwargs,
                'exception': str(exc),
            }
        )

        # Track error in analytics
        try:
            from apps.analytics.models import ErrorAnalytics
            from apps.organizations.models import Organization

            # Try to get organization from task args/kwargs
            organization_id = kwargs.get('organization_id') or (args[0] if args and isinstance(args[0], str) else None)

            if organization_id:
                try:
                    organization = Organization.objects.get(id=organization_id)

                    ErrorAnalytics.objects.create(
                        organization=organization,
                        error_type='system_error',
                        error_message=str(exc),
                        severity='medium',
                        context_data={
                            'task_name': self.name,
                            'task_id': task_id,
                            'args': str(args),
                            'kwargs': str(kwargs),
                        }
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def on_success(self, retval, task_id, args, kwargs):
        """Task success handler"""
        import logging
        logger = logging.getLogger(__name__)

        logger.debug(f"Task {self.name} completed successfully: {task_id}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Task retry handler"""
        import logging
        logger = logging.getLogger(__name__)

        logger.warning(
            f"Task {self.name} retrying: {exc}",
            extra={
                'task_id': task_id,
                'task_name': self.name,
                'retry_count': self.request.retries,
                'exception': str(exc),
            }
        )


# Set base task class
app.Task = BaseTask


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')
    return 'Debug task completed'


@app.task
def health_check_task():
    """Health check task for monitoring"""
    from apps.core.utils import HealthChecker

    health_status = HealthChecker.get_system_health()
    return health_status


# Celery signal handlers
from celery.signals import worker_ready, worker_shutdown, task_prerun, task_postrun


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handler for when worker is ready"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker {sender} is ready")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Handler for when worker shuts down"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker {sender} is shutting down")


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Handler before task execution"""
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Task {task.name} starting: {task_id}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Handler after task execution"""
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Task {task.name} finished: {task_id} (state: {state})")


# Custom task for calculating all metrics
@app.task
def calculate_all_metrics():
    """Calculate all active metric values"""
    from apps.analytics.models import MetricDefinition
    from apps.core.tasks import calculate_metric_values

    active_metrics = MetricDefinition.objects.filter(is_active=True)

    for metric in active_metrics:
        calculate_metric_values.delay(str(metric.id))

    return f"Scheduled calculation for {active_metrics.count()} metrics"


# Custom task for workflow health monitoring
@app.task
def monitor_workflow_health():
    """Monitor workflow execution health"""
    from apps.workflows.models import WorkflowExecution
    from apps.analytics.models import ErrorAnalytics
    from django.utils import timezone
    from datetime import timedelta

    # Check for workflows that have been running too long
    long_running_threshold = timezone.now() - timedelta(hours=1)
    long_running_executions = WorkflowExecution.objects.filter(
        status='running',
        started_at__lt=long_running_threshold
    )

    # Check for high error rates
    recent_threshold = timezone.now() - timedelta(minutes=30)
    recent_executions = WorkflowExecution.objects.filter(started_at__gte=recent_threshold)
    total_recent = recent_executions.count()
    failed_recent = recent_executions.filter(status='failed').count()

    error_rate = (failed_recent / total_recent * 100) if total_recent > 0 else 0

    health_report = {
        'long_running_executions': long_running_executions.count(),
        'recent_error_rate': round(error_rate, 2),
        'total_recent_executions': total_recent,
        'failed_recent_executions': failed_recent,
        'timestamp': timezone.now().isoformat()
    }

    # Log alerts if necessary
    if error_rate > 10:  # 10% error rate threshold
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"High error rate detected: {error_rate}%")

    return health_report


# Export the Celery app
__all__ = ['app']