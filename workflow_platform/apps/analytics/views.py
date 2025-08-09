"""
Analytics Views - Comprehensive analytics and business intelligence
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum, Max, Min
from django.utils import timezone
from datetime import timedelta, datetime
import json

from .models import (
    AnalyticsDashboard, MetricDefinition, MetricValue, PerformanceSnapshot,
    UsageStatistics, ErrorAnalytics, AlertRule, AlertInstance,
    BusinessMetrics, ReportTemplate, GeneratedReport
)
from .serializers import (
    AnalyticsDashboardSerializer, MetricDefinitionSerializer, MetricValueSerializer,
    PerformanceSnapshotSerializer, UsageStatisticsSerializer, ErrorAnalyticsSerializer,
    AlertRuleSerializer, AlertInstanceSerializer, BusinessMetricsSerializer,
    ReportTemplateSerializer, GeneratedReportSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.workflows.models import Workflow, WorkflowExecution
from apps.nodes.models import NodeExecutionLog


class AnalyticsDashboardViewSet(viewsets.ModelViewSet):
    """
    Analytics dashboard management
    """
    serializer_class = AnalyticsDashboardSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['dashboard_type', 'is_public']
    ordering = ['-updated_at']

    def get_queryset(self):
        """Get dashboards for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        user = self.request.user

        return AnalyticsDashboard.objects.filter(
            Q(organization=organization) &
            (Q(created_by=user) | Q(is_public=True) | Q(shared_with_users=user))
        ).distinct()

    def perform_create(self, serializer):
        """Create dashboard with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['get'])
    def data(self, request, pk=None):
        """Get dashboard data"""
        dashboard = self.get_object()

        # Get date range from query params
        end_date = timezone.now()
        days = int(request.query_params.get('days', 30))
        start_date = end_date - timedelta(days=days)

        dashboard_data = {}

        # Process each widget in the dashboard
        for widget in dashboard.widgets:
            widget_id = widget.get('id')
            widget_type = widget.get('type')
            widget_config = widget.get('config', {})

            try:
                if widget_type == 'metric_chart':
                    dashboard_data[widget_id] = self._get_metric_chart_data(
                        widget_config, start_date, end_date
                    )
                elif widget_type == 'performance_overview':
                    dashboard_data[widget_id] = self._get_performance_overview_data(
                        start_date, end_date
                    )
                elif widget_type == 'workflow_stats':
                    dashboard_data[widget_id] = self._get_workflow_stats_data(
                        start_date, end_date
                    )
                elif widget_type == 'error_analysis':
                    dashboard_data[widget_id] = self._get_error_analysis_data(
                        start_date, end_date
                    )
                elif widget_type == 'usage_trends':
                    dashboard_data[widget_id] = self._get_usage_trends_data(
                        start_date, end_date
                    )
                else:
                    dashboard_data[widget_id] = {'error': 'Unknown widget type'}

            except Exception as e:
                dashboard_data[widget_id] = {'error': str(e)}

        return Response({
            'dashboard_id': dashboard.id,
            'data': dashboard_data,
            'generated_at': timezone.now()
        })

    def _get_metric_chart_data(self, config, start_date, end_date):
        """Get metric chart data"""
        metric_ids = config.get('metrics', [])

        chart_data = []
        for metric_id in metric_ids:
            try:
                metric = MetricDefinition.objects.get(id=metric_id)
                values = MetricValue.objects.filter(
                    metric_definition=metric,
                    timestamp__range=[start_date, end_date]
                ).order_by('timestamp')

                data_points = [{
                    'timestamp': value.timestamp.isoformat(),
                    'value': value.value
                } for value in values]

                chart_data.append({
                    'metric_id': metric_id,
                    'metric_name': metric.name,
                    'data': data_points
                })
            except MetricDefinition.DoesNotExist:
                continue

        return chart_data

    def _get_performance_overview_data(self, start_date, end_date):
        """Get performance overview data"""
        organization = self.request.user.organization_memberships.first().organization

        # Get latest performance snapshot
        latest_snapshot = PerformanceSnapshot.objects.filter(
            organization=organization
        ).order_by('-snapshot_time').first()

        # Get execution performance
        executions = WorkflowExecution.objects.filter(
            workflow__organization=organization,
            started_at__range=[start_date, end_date]
        )

        avg_execution_time = executions.filter(
            status='completed',
            execution_time__isnull=False
        ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

        success_rate = 0
        if executions.count() > 0:
            successful = executions.filter(status='completed').count()
            success_rate = (successful / executions.count()) * 100

        return {
            'system_performance': {
                'cpu_usage': latest_snapshot.cpu_usage_percent if latest_snapshot else 0,
                'memory_usage': latest_snapshot.memory_usage_mb if latest_snapshot else 0,
                'active_executions': latest_snapshot.running_executions if latest_snapshot else 0,
            },
            'execution_performance': {
                'avg_execution_time_ms': round(avg_execution_time, 2),
                'success_rate': round(success_rate, 2),
                'total_executions': executions.count(),
            }
        }

    def _get_workflow_stats_data(self, start_date, end_date):
        """Get workflow statistics data"""
        organization = self.request.user.organization_memberships.first().organization

        workflows = Workflow.objects.filter(organization=organization)
        executions = WorkflowExecution.objects.filter(
            workflow__organization=organization,
            started_at__range=[start_date, end_date]
        )

        # Top performing workflows
        top_workflows = workflows.annotate(
            execution_count=Count('executions', filter=Q(
                executions__started_at__range=[start_date, end_date]
            ))
        ).order_by('-execution_count')[:5]

        return {
            'total_workflows': workflows.count(),
            'active_workflows': workflows.filter(status='active').count(),
            'total_executions': executions.count(),
            'top_workflows': [{
                'id': w.id,
                'name': w.name,
                'execution_count': w.execution_count
            } for w in top_workflows]
        }

    def _get_error_analysis_data(self, start_date, end_date):
        """Get error analysis data"""
        organization = self.request.user.organization_memberships.first().organization

        errors = ErrorAnalytics.objects.filter(
            organization=organization,
            first_seen__range=[start_date, end_date]
        )

        # Error types breakdown
        error_types = errors.values('error_type').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Severity breakdown
        severity_breakdown = errors.values('severity').annotate(
            count=Count('id')
        )

        return {
            'total_errors': errors.count(),
            'unresolved_errors': errors.filter(is_resolved=False).count(),
            'error_types': list(error_types),
            'severity_breakdown': list(severity_breakdown)
        }

    def _get_usage_trends_data(self, start_date, end_date):
        """Get usage trends data"""
        organization = self.request.user.organization_memberships.first().organization

        usage_stats = UsageStatistics.objects.filter(
            organization=organization,
            date__range=[start_date.date(), end_date.date()]
        ).order_by('date')

        trends = [{
            'date': stat.date.isoformat(),
            'executions': stat.total_executions,
            'api_calls': stat.api_calls,
            'active_users': stat.active_users
        } for stat in usage_stats]

        return {
            'trends': trends,
            'total_period_executions': sum(stat.total_executions for stat in usage_stats),
            'total_period_api_calls': sum(stat.api_calls for stat in usage_stats)
        }


class MetricDefinitionViewSet(viewsets.ModelViewSet):
    """
    Custom metric definition management
    """
    serializer_class = MetricDefinitionSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['metric_type', 'aggregation_period', 'is_active']
    ordering = ['name']

    def get_queryset(self):
        """Get metrics for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return MetricDefinition.objects.filter(organization=organization)

    def perform_create(self, serializer):
        """Create metric with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['get'])
    def values(self, request, pk=None):
        """Get metric values"""
        metric = self.get_object()

        # Get date range
        end_date = timezone.now()
        days = int(request.query_params.get('days', 30))
        start_date = end_date - timedelta(days=days)

        values = metric.values.filter(
            timestamp__range=[start_date, end_date]
        ).order_by('timestamp')

        serializer = MetricValueSerializer(values, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Trigger metric calculation"""
        metric = self.get_object()

        try:
            # This would trigger the metric calculation task
            from .tasks import calculate_metric_values
            calculate_metric_values.delay(metric.id)

            return Response({'message': 'Metric calculation started'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overview_analytics(request):
    """Get organization overview analytics"""

    organization = request.user.organization_memberships.first().organization

    # Get date range
    end_date = timezone.now()
    days = int(request.query_params.get('days', 30))
    start_date = end_date - timedelta(days=days)

    # Workflow metrics
    workflows = Workflow.objects.filter(organization=organization)
    executions = WorkflowExecution.objects.filter(
        workflow__organization=organization,
        started_at__range=[start_date, end_date]
    )

    # Node execution metrics
    node_executions = NodeExecutionLog.objects.filter(
        execution__workflow__organization=organization,
        started_at__range=[start_date, end_date]
    )

    # Calculate metrics
    total_executions = executions.count()
    successful_executions = executions.filter(status='completed').count()
    failed_executions = executions.filter(status='failed').count()

    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

    avg_execution_time = executions.filter(
        status='completed',
        execution_time__isnull=False
    ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

    # Daily breakdown
    daily_stats = []
    for i in range(days):
        date = (end_date - timedelta(days=i)).date()
        day_executions = executions.filter(started_at__date=date)

        daily_stats.append({
            'date': date.isoformat(),
            'executions': day_executions.count(),
            'successful': day_executions.filter(status='completed').count(),
            'failed': day_executions.filter(status='failed').count(),
        })

    # Top workflows
    top_workflows = workflows.annotate(
        execution_count=Count('executions', filter=Q(
            executions__started_at__range=[start_date, end_date]
        ))
    ).order_by('-execution_count')[:5]

    # Node performance
    node_performance = node_executions.values('node_type__name').annotate(
        total_executions=Count('id'),
        avg_execution_time=Avg('execution_time'),
        success_rate=Count('id', filter=Q(status='completed')) * 100.0 / Count('id')
    ).order_by('-total_executions')[:10]

    # Error analysis
    recent_errors = ErrorAnalytics.objects.filter(
        organization=organization,
        first_seen__range=[start_date, end_date]
    ).order_by('-occurrence_count')[:5]

    analytics_data = {
        'overview': {
            'total_workflows': workflows.count(),
            'active_workflows': workflows.filter(status='active').count(),
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': round(success_rate, 2),
            'avg_execution_time_ms': round(avg_execution_time, 2),
        },
        'daily_stats': daily_stats,
        'top_workflows': [{
            'id': w.id,
            'name': w.name,
            'execution_count': w.execution_count
        } for w in top_workflows],
        'node_performance': list(node_performance),
        'recent_errors': [{
            'error_type': error.error_type,
            'error_message': error.error_message[:100],
            'occurrence_count': error.occurrence_count,
            'severity': error.severity
        } for error in recent_errors]
    }

    return Response(analytics_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def performance_analytics(request):
    """Get performance analytics"""

    organization = request.user.organization_memberships.first().organization

    # Get recent performance snapshots
    snapshots = PerformanceSnapshot.objects.filter(
        organization=organization
    ).order_by('-snapshot_time')[:100]  # Last 100 snapshots

    if not snapshots:
        return Response({
            'message': 'No performance data available',
            'snapshots': []
        })

    # Calculate performance trends
    performance_data = {
        'current_performance': {
            'cpu_usage': snapshots[0].cpu_usage_percent,
            'memory_usage': snapshots[0].memory_usage_mb,
            'active_executions': snapshots[0].running_executions,
            'avg_execution_time': snapshots[0].avg_execution_time_ms,
            'error_rate': snapshots[0].error_rate_percent,
        },
        'trends': [{
            'timestamp': snapshot.snapshot_time.isoformat(),
            'cpu_usage': snapshot.cpu_usage_percent,
            'memory_usage': snapshot.memory_usage_mb,
            'execution_time': snapshot.avg_execution_time_ms,
            'error_rate': snapshot.error_rate_percent,
        } for snapshot in snapshots[::-1]],  # Reverse for chronological order
        'averages': {
            'avg_cpu': round(sum(s.cpu_usage_percent for s in snapshots) / len(snapshots), 2),
            'avg_memory': round(sum(s.memory_usage_mb for s in snapshots) / len(snapshots), 2),
            'avg_execution_time': round(sum(s.avg_execution_time_ms for s in snapshots) / len(snapshots), 2),
        }
    }

    return Response(performance_data)


@api_view(['GET'])
@permission_calls([IsAuthenticated])
def usage_analytics(request):
    """Get usage analytics"""

    organization = request.user.organization_memberships.first().organization

    # Get date range
    end_date = timezone.now().date()
    days = int(request.query_params.get('days', 30))
    start_date = end_date - timedelta(days=days)

    # Get usage statistics
    usage_stats = UsageStatistics.objects.filter(
        organization=organization,
        date__range=[start_date, end_date]
    ).order_by('date')

    # Calculate totals and trends
    total_executions = sum(stat.total_executions for stat in usage_stats)
    total_api_calls = sum(stat.api_calls for stat in usage_stats)
    total_compute_time = sum(stat.compute_time_seconds for stat in usage_stats)

    # Daily usage trends
    usage_trends = [{
        'date': stat.date.isoformat(),
        'executions': stat.total_executions,
        'api_calls': stat.api_calls,
        'active_users': stat.active_users,
        'compute_time': stat.compute_time_seconds,
        'estimated_cost': float(stat.estimated_cost)
    } for stat in usage_stats]

    # Node usage breakdown
    node_usage = {}
    for stat in usage_stats:
        for node_type, count in stat.node_executions.items():
            node_usage[node_type] = node_usage.get(node_type, 0) + count

    # Sort by usage
    top_nodes = sorted(node_usage.items(), key=lambda x: x[1], reverse=True)[:10]

    usage_data = {
        'summary': {
            'total_executions': total_executions,
            'total_api_calls': total_api_calls,
            'total_compute_time_hours': round(total_compute_time / 3600, 2),
            'avg_daily_executions': round(total_executions / max(days, 1), 2),
        },
        'trends': usage_trends,
        'top_node_types': [{
            'node_type': node_type,
            'execution_count': count
        } for node_type, count in top_nodes],
        'period_start': start_date.isoformat(),
        'period_end': end_date.isoformat()
    }

    return Response(usage_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def business_analytics(request):
    """Get business analytics and ROI metrics"""

    organization = request.user.organization_memberships.first().organization

    # Get date range
    end_date = timezone.now().date()
    days = int(request.query_params.get('days', 90))  # Default to 90 days for business metrics
    start_date = end_date - timedelta(days=days)

    # Get business metrics
    business_metrics = BusinessMetrics.objects.filter(
        organization=organization,
        date__range=[start_date, end_date]
    ).order_by('date')

    # Calculate business KPIs
    total_cost_savings = sum(float(metric.estimated_cost_savings) for metric in business_metrics)
    total_hours_saved = sum(metric.automation_hours_saved for metric in business_metrics)
    total_workflows_automated = sum(metric.workflows_automated for metric in business_metrics)

    # User adoption metrics
    latest_metric = business_metrics.last()
    current_adoption_rate = latest_metric.workflow_adoption_rate if latest_metric else 0

    # Calculate ROI
    total_executions = sum(metric.total_executions for metric in business_metrics)
    avg_execution_value = sum(float(metric.avg_execution_value) for metric in business_metrics) / max(
        len(business_metrics), 1)
    estimated_total_value = total_executions * avg_execution_value

    # Monthly trends
    monthly_trends = [{
        'date': metric.date.isoformat(),
        'cost_savings': float(metric.estimated_cost_savings),
        'hours_saved': metric.automation_hours_saved,
        'active_users': metric.active_users,
        'new_workflows': metric.new_workflows_created,
        'adoption_rate': metric.workflow_adoption_rate
    } for metric in business_metrics]

    business_data = {
        'roi_summary': {
            'total_cost_savings': round(total_cost_savings, 2),
            'total_hours_saved': round(total_hours_saved, 2),
            'total_workflows_automated': total_workflows_automated,
            'estimated_total_value': round(estimated_total_value, 2),
            'current_adoption_rate': round(current_adoption_rate, 2),
        },
        'efficiency_gains': {
            'manual_processes_replaced': sum(metric.manual_processes_replaced for metric in business_metrics),
            'avg_error_reduction': round(
                sum(metric.error_reduction_percent for metric in business_metrics) / max(len(business_metrics), 1), 2),
            'automation_rate': round((total_workflows_automated / max(organization.workflows.count(), 1)) * 100, 2)
        },
        'trends': monthly_trends,
        'period_start': start_date.isoformat(),
        'period_end': end_date.isoformat()
    }

    return Response(business_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def real_time_metrics(request):
    """Get real-time system metrics"""

    organization = request.user.organization_memberships.first().organization

    # Get current system status
    now = timezone.now()

    # Running executions
    running_executions = WorkflowExecution.objects.filter(
        workflow__organization=organization,
        status='running'
    ).count()

    # Executions in last hour
    last_hour = now - timedelta(hours=1)
    recent_executions = WorkflowExecution.objects.filter(
        workflow__organization=organization,
        started_at__gte=last_hour
    )

    # Error rate in last hour
    recent_errors = recent_executions.filter(status='failed').count()
    error_rate = (recent_errors / max(recent_executions.count(), 1)) * 100

    # Latest performance snapshot
    latest_performance = PerformanceSnapshot.objects.filter(
        organization=organization
    ).order_by('-snapshot_time').first()

    # Active alerts
    active_alerts = AlertInstance.objects.filter(
        alert_rule__organization=organization,
        status='firing'
    ).count()

    real_time_data = {
        'current_status': {
            'running_executions': running_executions,
            'executions_last_hour': recent_executions.count(),
            'error_rate_last_hour': round(error_rate, 2),
            'active_alerts': active_alerts,
        },
        'system_performance': {
            'cpu_usage': latest_performance.cpu_usage_percent if latest_performance else 0,
            'memory_usage': latest_performance.memory_usage_mb if latest_performance else 0,
            'api_response_time': latest_performance.api_response_time_ms if latest_performance else 0,
        } if latest_performance else {},
        'timestamp': now.isoformat()
    }

    return Response(real_time_data)


class ErrorAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Error analytics and monitoring
    """
    serializer_class = ErrorAnalyticsSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['error_type', 'severity', 'is_resolved']
    ordering = ['-occurrence_count', '-last_seen']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get errors for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ErrorAnalytics.objects.filter(organization=organization)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark error as resolved"""
        error = self.get_object()

        error.is_resolved = True
        error.resolved_at = timezone.now()
        error.resolved_by = request.user
        error.resolution_notes = request.data.get('notes', '')
        error.save()

        return Response({'message': 'Error marked as resolved'})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get error summary statistics"""
        organization = request.user.organization_memberships.first().organization

        errors = self.get_queryset()

        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        recent_errors = errors.filter(first_seen__gte=start_date)

        summary = {
            'total_errors': errors.count(),
            'unresolved_errors': errors.filter(is_resolved=False).count(),
            'recent_errors': recent_errors.count(),
            'critical_errors': errors.filter(severity='critical', is_resolved=False).count(),
            'error_types': list(errors.values('error_type').annotate(
                count=Count('id')
            ).order_by('-count')[:5]),
            'top_workflows': list(errors.exclude(workflow__isnull=True).values(
                'workflow__name'
            ).annotate(count=Count('id')).order_by('-count')[:5])
        }

        return Response(summary)


class AlertRuleViewSet(viewsets.ModelViewSet):
    """
    Alert rule management
    """
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'condition_type']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get alert rules for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AlertRule.objects.filter(organization=organization)

    def perform_create(self, serializer):
        """Create alert rule with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test alert rule"""
        alert_rule = self.get_object()

        try:
            # This would trigger alert rule evaluation
            from .tasks import evaluate_alert_rule
            result = evaluate_alert_rule.delay(alert_rule.id)

            return Response({
                'message': 'Alert rule test started',
                'task_id': result.id
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )