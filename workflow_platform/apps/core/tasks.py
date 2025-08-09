"""
Celery Tasks for Background Processing
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django.db.models import Count, Avg, Sum
from django.conf import settings
from datetime import timedelta, datetime
import asyncio
import json
import traceback

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def execute_workflow_task(self, workflow_id, input_data=None, triggered_by_user_id=None, trigger_source='scheduled'):
    """
    Execute workflow in background
    """
    try:
        from apps.workflows.models import Workflow
        from apps.core.workflow_engine import workflow_engine

        workflow = Workflow.objects.get(id=workflow_id)

        logger.info(f"Executing workflow {workflow.name} (ID: {workflow_id})")

        # Execute workflow
        execution = asyncio.run(
            workflow_engine.execute_workflow(
                workflow=workflow,
                input_data=input_data or {},
                triggered_by_user_id=triggered_by_user_id,
                trigger_source=trigger_source
            )
        )

        logger.info(f"Workflow {workflow.name} executed successfully: {execution.id}")

        return {
            'status': 'success',
            'execution_id': str(execution.id),
            'workflow_id': str(workflow_id)
        }

    except Exception as exc:
        logger.error(f"Workflow execution failed: {str(exc)}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)

        return {
            'status': 'failed',
            'error': str(exc),
            'workflow_id': str(workflow_id)
        }


@shared_task
def schedule_workflow_executions():
    """
    Check and schedule workflows that need to run
    """
    try:
        from apps.workflows.models import Workflow
        from croniter import croniter

        now = timezone.now()

        # Get workflows with schedule that need to run
        scheduled_workflows = Workflow.objects.filter(
            status='active',
            trigger_type='schedule',
            schedule_expression__isnull=False
        ).exclude(schedule_expression='')

        scheduled_count = 0

        for workflow in scheduled_workflows:
            try:
                # Check if workflow should run now
                cron = croniter(workflow.schedule_expression, now)
                next_run = cron.get_next(datetime)

                # If next run is within the next minute, schedule it
                if next_run <= now + timedelta(minutes=1):
                    execute_workflow_task.delay(
                        workflow_id=str(workflow.id),
                        trigger_source='scheduled'
                    )

                    # Update next run time
                    workflow.next_run_at = next_run
                    workflow.save(update_fields=['next_run_at'])

                    scheduled_count += 1
                    logger.info(f"Scheduled workflow: {workflow.name}")

            except Exception as e:
                logger.error(f"Error scheduling workflow {workflow.name}: {str(e)}")

        logger.info(f"Scheduled {scheduled_count} workflows")

        return {'scheduled_workflows': scheduled_count}

    except Exception as e:
        logger.error(f"Error in schedule_workflow_executions: {str(e)}")
        return {'error': str(e)}


@shared_task
def cleanup_old_executions():
    """
    Cleanup old execution records
    """
    try:
        from apps.workflows.models import WorkflowExecution
        from apps.nodes.models import NodeExecutionLog

        # Get cleanup settings
        retention_days = getattr(settings, 'EXECUTION_RETENTION_DAYS', 90)
        cutoff_date = timezone.now() - timedelta(days=retention_days)

        # Delete old executions
        old_executions = WorkflowExecution.objects.filter(started_at__lt=cutoff_date)
        execution_count = old_executions.count()
        old_executions.delete()

        # Delete old node logs
        old_logs = NodeExecutionLog.objects.filter(started_at__lt=cutoff_date)
        log_count = old_logs.count()
        old_logs.delete()

        logger.info(f"Cleaned up {execution_count} executions and {log_count} node logs")

        return {
            'executions_deleted': execution_count,
            'logs_deleted': log_count
        }

    except Exception as e:
        logger.error(f"Error in cleanup_old_executions: {str(e)}")
        return {'error': str(e)}


@shared_task
def calculate_usage_statistics():
    """
    Calculate daily usage statistics for all organizations
    """
    try:
        from apps.organizations.models import Organization
        from apps.analytics.models import UsageStatistics
        from apps.workflows.models import WorkflowExecution
        from apps.webhooks.models import WebhookDelivery
        from django.contrib.auth.models import User

        yesterday = timezone.now().date() - timedelta(days=1)

        for organization in Organization.objects.all():
            try:
                # Get executions for yesterday
                executions = WorkflowExecution.objects.filter(
                    workflow__organization=organization,
                    started_at__date=yesterday
                )

                # Get webhook deliveries
                webhooks = WebhookDelivery.objects.filter(
                    webhook_endpoint__organization=organization,
                    received_at__date=yesterday
                )

                # Get active users
                active_users = User.objects.filter(
                    organization_memberships__organization=organization,
                    last_login__date=yesterday
                ).count()

                # Calculate metrics
                total_executions = executions.count()
                successful_executions = executions.filter(status='completed').count()
                failed_executions = executions.filter(status='failed').count()

                avg_execution_time = executions.filter(
                    status='completed',
                    execution_time__isnull=False
                ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

                # Calculate compute time (simplified)
                compute_time = sum(
                    exec.execution_time or 0 for exec in executions.filter(status='completed')
                )

                # Create or update usage statistics
                usage_stat, created = UsageStatistics.objects.update_or_create(
                    organization=organization,
                    date=yesterday,
                    defaults={
                        'total_executions': total_executions,
                        'successful_executions': successful_executions,
                        'failed_executions': failed_executions,
                        'avg_execution_time_ms': avg_execution_time,
                        'webhook_deliveries': webhooks.count(),
                        'active_users': active_users,
                        'compute_time_seconds': compute_time / 1000,  # Convert ms to seconds
                    }
                )

                logger.info(f"Updated usage statistics for {organization.name}")

            except Exception as e:
                logger.error(f"Error calculating usage for {organization.name}: {str(e)}")

        return {'status': 'completed'}

    except Exception as e:
        logger.error(f"Error in calculate_usage_statistics: {str(e)}")
        return {'error': str(e)}


@shared_task
def capture_performance_snapshot():
    """
    Capture system performance snapshots
    """
    try:
        from apps.analytics.models import PerformanceSnapshot
        from apps.organizations.models import Organization
        from apps.workflows.models import WorkflowExecution
        import psutil
        import redis

        # Get system metrics
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Get Redis memory usage
        redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        redis_info = redis_client.info('memory')
        redis_memory_mb = redis_info.get('used_memory', 0) / (1024 * 1024)

        # Get database connections (simplified)
        from django.db import connection
        db_connections = len(connection.queries)

        for organization in Organization.objects.all():
            try:
                # Get organization-specific metrics
                running_executions = WorkflowExecution.objects.filter(
                    workflow__organization=organization,
                    status='running'
                ).count()

                queued_executions = WorkflowExecution.objects.filter(
                    workflow__organization=organization,
                    status='pending'
                ).count()

                # Calculate recent performance metrics
                recent_executions = WorkflowExecution.objects.filter(
                    workflow__organization=organization,
                    started_at__gte=timezone.now() - timedelta(hours=1)
                )

                avg_execution_time = recent_executions.filter(
                    status='completed',
                    execution_time__isnull=False
                ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

                error_rate = 0
                if recent_executions.count() > 0:
                    failed_count = recent_executions.filter(status='failed').count()
                    error_rate = (failed_count / recent_executions.count()) * 100

                # Create performance snapshot
                PerformanceSnapshot.objects.create(
                    organization=organization,
                    cpu_usage_percent=cpu_usage,
                    memory_usage_mb=memory.used / (1024 * 1024),
                    disk_usage_percent=disk.percent,
                    active_workflows=organization.workflows.filter(status='active').count(),
                    running_executions=running_executions,
                    queued_executions=queued_executions,
                    avg_execution_time_ms=avg_execution_time,
                    error_rate_percent=error_rate,
                    database_connections=db_connections,
                    redis_memory_mb=redis_memory_mb
                )

            except Exception as e:
                logger.error(f"Error capturing performance for {organization.name}: {str(e)}")

        logger.info("Performance snapshots captured for all organizations")
        return {'status': 'completed'}

    except Exception as e:
        logger.error(f"Error in capture_performance_snapshot: {str(e)}")
        return {'error': str(e)}


@shared_task
def calculate_metric_values(metric_definition_id):
    """
    Calculate metric values for a specific metric definition
    """
    try:
        from apps.analytics.models import MetricDefinition, MetricValue
        from apps.workflows.models import WorkflowExecution
        from apps.nodes.models import NodeExecutionLog

        metric = MetricDefinition.objects.get(id=metric_definition_id)

        # Determine time window based on aggregation period
        now = timezone.now()
        if metric.aggregation_period == 'hour':
            start_time = now.replace(minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=1)
        elif metric.aggregation_period == 'day':
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)
        elif metric.aggregation_period == 'week':
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(weeks=1)
        elif metric.aggregation_period == 'month':
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start_time.month == 12:
                end_time = start_time.replace(year=start_time.year + 1, month=1)
            else:
                end_time = start_time.replace(month=start_time.month + 1)
        else:
            return {'error': 'Invalid aggregation period'}

        # Calculate metric value based on type and source
        if metric.source_model == 'WorkflowExecution':
            queryset = WorkflowExecution.objects.filter(
                workflow__organization=metric.organization,
                started_at__gte=start_time,
                started_at__lt=end_time
            )
        elif metric.source_model == 'NodeExecutionLog':
            queryset = NodeExecutionLog.objects.filter(
                execution__workflow__organization=metric.organization,
                started_at__gte=start_time,
                started_at__lt=end_time
            )
        else:
            return {'error': 'Unsupported source model'}

        # Apply filters
        for field, value in metric.filters.items():
            queryset = queryset.filter(**{field: value})

        # Calculate value based on metric type
        if metric.metric_type == 'count':
            value = queryset.count()
        elif metric.metric_type == 'sum':
            value = queryset.aggregate(total=Sum(metric.source_field))['total'] or 0
        elif metric.metric_type == 'average':
            value = queryset.aggregate(avg=Avg(metric.source_field))['avg'] or 0
        elif metric.metric_type == 'percentage':
            total = queryset.count()
            subset = queryset.filter(**{metric.source_field: True}).count()
            value = (subset / total * 100) if total > 0 else 0
        else:
            return {'error': 'Unsupported metric type'}

        # Store metric value
        MetricValue.objects.update_or_create(
            metric_definition=metric,
            timestamp=start_time,
            defaults={'value': value}
        )

        logger.info(f"Calculated metric {metric.name}: {value}")

        return {
            'metric_id': str(metric.id),
            'value': value,
            'timestamp': start_time.isoformat()
        }

    except Exception as e:
        logger.error(f"Error calculating metric values: {str(e)}")
        return {'error': str(e)}


@shared_task
def evaluate_alert_rules():
    """
    Evaluate all active alert rules
    """
    try:
        from apps.analytics.models import AlertRule, AlertInstance, MetricValue

        active_rules = AlertRule.objects.filter(is_active=True)

        for rule in active_rules:
            try:
                # Check cooldown period
                if rule.last_triggered:
                    cooldown_until = rule.last_triggered + timedelta(minutes=rule.cooldown_minutes)
                    if timezone.now() < cooldown_until:
                        continue

                # Get recent metric values
                window_start = timezone.now() - timedelta(minutes=rule.evaluation_window_minutes)
                recent_values = MetricValue.objects.filter(
                    metric_definition=rule.metric,
                    timestamp__gte=window_start
                ).order_by('-timestamp')

                if not recent_values:
                    continue

                # Get latest value
                latest_value = recent_values.first().value

                # Evaluate condition
                condition_met = False
                if rule.operator == '>':
                    condition_met = latest_value > rule.threshold_value
                elif rule.operator == '<':
                    condition_met = latest_value < rule.threshold_value
                elif rule.operator == '>=':
                    condition_met = latest_value >= rule.threshold_value
                elif rule.operator == '<=':
                    condition_met = latest_value <= rule.threshold_value
                elif rule.operator == '=':
                    condition_met = latest_value == rule.threshold_value
                elif rule.operator == '!=':
                    condition_met = latest_value != rule.threshold_value

                if condition_met:
                    # Create alert instance
                    alert_instance = AlertInstance.objects.create(
                        alert_rule=rule,
                        triggered_value=latest_value,
                        threshold_value=rule.threshold_value,
                        status='firing'
                    )

                    # Update rule
                    rule.last_triggered = timezone.now()
                    rule.trigger_count += 1
                    rule.save()

                    # Send notifications
                    send_alert_notifications.delay(alert_instance.id)

                    logger.info(f"Alert triggered: {rule.name}")

            except Exception as e:
                logger.error(f"Error evaluating alert rule {rule.name}: {str(e)}")

        return {'status': 'completed'}

    except Exception as e:
        logger.error(f"Error in evaluate_alert_rules: {str(e)}")
        return {'error': str(e)}


@shared_task
def send_alert_notifications(alert_instance_id):
    """
    Send notifications for alert instance
    """
    try:
        from apps.analytics.models import AlertInstance
        from django.core.mail import send_mail
        import requests

        alert_instance = AlertInstance.objects.get(id=alert_instance_id)
        alert_rule = alert_instance.alert_rule

        # Prepare notification message
        message = f"""
        Alert: {alert_rule.name}

        Metric: {alert_rule.metric.name}
        Current Value: {alert_instance.triggered_value}
        Threshold: {alert_instance.threshold_value}
        Condition: {alert_rule.operator} {alert_rule.threshold_value}

        Triggered at: {alert_instance.triggered_at}
        Organization: {alert_rule.organization.name}
        """

        notifications_sent = []

        # Send notifications based on configured channels
        for channel in alert_rule.notification_channels:
            try:
                if channel['type'] == 'email':
                    send_mail(
                        subject=f"Alert: {alert_rule.name}",
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=channel['config']['recipients'],
                        fail_silently=False
                    )
                    notifications_sent.append('email')

                elif channel['type'] == 'webhook':
                    response = requests.post(
                        channel['config']['url'],
                        json={
                            'alert_name': alert_rule.name,
                            'metric_name': alert_rule.metric.name,
                            'current_value': alert_instance.triggered_value,
                            'threshold_value': alert_instance.threshold_value,
                            'triggered_at': alert_instance.triggered_at.isoformat(),
                            'organization': alert_rule.organization.name
                        },
                        timeout=30
                    )
                    if response.status_code == 200:
                        notifications_sent.append('webhook')

                elif channel['type'] == 'slack':
                    # Implement Slack notification
                    pass

            except Exception as e:
                logger.error(f"Failed to send {channel['type']} notification: {str(e)}")

        # Update alert instance
        alert_instance.notifications_sent = notifications_sent
        alert_instance.save()

        logger.info(f"Sent notifications for alert {alert_rule.name}: {notifications_sent}")

        return {'notifications_sent': notifications_sent}

    except Exception as e:
        logger.error(f"Error sending alert notifications: {str(e)}")
        return {'error': str(e)}


@shared_task
def generate_scheduled_reports():
    """
    Generate scheduled reports
    """
    try:
        from apps.analytics.models import ReportTemplate, GeneratedReport

        now = timezone.now()

        # Check for reports that need to be generated
        scheduled_reports = ReportTemplate.objects.filter(
            is_active=True,
            frequency__in=['daily', 'weekly', 'monthly']
        )

        for report_template in scheduled_reports:
            try:
                should_generate = False

                if report_template.frequency == 'daily':
                    # Check if we should generate daily report
                    if not report_template.last_generated or \
                            report_template.last_generated.date() < now.date():
                        should_generate = True

                elif report_template.frequency == 'weekly':
                    # Check if we should generate weekly report (e.g., every Monday)
                    if now.weekday() == 0:  # Monday
                        if not report_template.last_generated or \
                                (now - report_template.last_generated).days >= 7:
                            should_generate = True

                elif report_template.frequency == 'monthly':
                    # Check if we should generate monthly report (first day of month)
                    if now.day == 1:
                        if not report_template.last_generated or \
                                report_template.last_generated.month != now.month:
                            should_generate = True

                if should_generate:
                    # Generate report
                    generate_report.delay(report_template.id)

                    # Update last generated time
                    report_template.last_generated = now
                    report_template.save()

            except Exception as e:
                logger.error(f"Error checking report template {report_template.name}: {str(e)}")

        return {'status': 'completed'}

    except Exception as e:
        logger.error(f"Error in generate_scheduled_reports: {str(e)}")
        return {'error': str(e)}


@shared_task
def generate_report(report_template_id):
    """
    Generate a specific report
    """
    try:
        from apps.analytics.models import ReportTemplate, GeneratedReport

        template = ReportTemplate.objects.get(id=report_template_id)

        # Determine report period
        now = timezone.now()
        if template.frequency == 'daily':
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            period_end = period_start + timedelta(days=1)
        elif template.frequency == 'weekly':
            period_start = now - timedelta(days=7)
            period_end = now
        elif template.frequency == 'monthly':
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            period_start = period_start.replace(day=1)
            period_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = now - timedelta(days=30)
            period_end = now

        # Create report record
        report = GeneratedReport.objects.create(
            template=template,
            title=f"{template.name} - {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}",
            period_start=period_start,
            period_end=period_end,
            generation_status='generating'
        )

        try:
            # Generate report data
            report_data = {}

            # This would implement actual report generation logic
            # For now, just create a placeholder
            report_data = {
                'template_name': template.name,
                'period': f"{period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}",
                'generated_at': now.isoformat(),
                'organization': template.organization.name,
                'sections': []
            }

            # Update report with data
            report.report_data = report_data
            report.generation_status = 'completed'
            report.save()

            logger.info(f"Generated report: {template.name}")

            return {
                'report_id': str(report.id),
                'status': 'completed'
            }

        except Exception as e:
            report.generation_status = 'failed'
            report.error_message = str(e)
            report.save()
            raise

    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return {'error': str(e)}


# Periodic task setup (would be configured in Celery beat schedule)
"""
CELERY_BEAT_SCHEDULE = {
    'schedule-workflow-executions': {
        'task': 'apps.core.tasks.schedule_workflow_executions',
        'schedule': 60.0,  # Every minute
    },
    'cleanup-old-executions': {
        'task': 'apps.core.tasks.cleanup_old_executions',
        'schedule': 86400.0,  # Daily
    },
    'calculate-usage-statistics': {
        'task': 'apps.core.tasks.calculate_usage_statistics',
        'schedule': 3600.0,  # Hourly
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
        'schedule': 3600.0,  # Hourly
    },
}
"""