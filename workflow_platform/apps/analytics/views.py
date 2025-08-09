"""
Analytics Views - Data analytics and reporting endpoints
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from datetime import timedelta, datetime
import json

from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsReport,
    AnalyticsMetric, UsageAnalytics, PerformanceMetrics, AnalyticsAlert
)
from .serializers import (
    AnalyticsDashboardSerializer, AnalyticsWidgetSerializer,
    AnalyticsReportSerializer, AnalyticsMetricSerializer,
    UsageAnalyticsSerializer, PerformanceMetricsSerializer,
    AnalyticsAlertSerializer, DashboardStatsSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.workflows.models import Workflow, WorkflowExecution
from apps.executions.models import ExecutionHistory


class AnalyticsDashboardViewSet(viewsets.ModelViewSet):
    """
    Analytics dashboard management
    """
    serializer_class = AnalyticsDashboardSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['dashboard_type', 'is_public', 'is_active']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get dashboards for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AnalyticsDashboard.objects.filter(
            Q(organization=organization) |
            Q(is_public=True) |
            Q(shared_with_users=self.request.user)
        ).distinct().select_related('organization', 'created_by')

    def perform_create(self, serializer):
        """Create dashboard with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share dashboard with users"""
        dashboard = self.get_object()
        user_ids = request.data.get('user_ids', [])

        # Check permissions
        if dashboard.organization != request.user.organization_memberships.first().organization:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.contrib.auth.models import User
        users = User.objects.filter(id__in=user_ids)
        dashboard.shared_with_users.set(users)

        return Response({'message': f'Dashboard shared with {len(users)} users'})

    @action(detail=True, methods=['get'])
    def data(self, request, pk=None):
        """Get dashboard data"""
        dashboard = self.get_object()

        # Get data for all widgets
        widget_data = {}
        for widget in dashboard.widgets.filter(is_active=True):
            try:
                data = self._get_widget_data(widget, request.query_params)
                widget_data[str(widget.id)] = data
            except Exception as e:
                widget_data[str(widget.id)] = {'error': str(e)}

        return Response({
            'dashboard': AnalyticsDashboardSerializer(dashboard).data,
            'widget_data': widget_data
        })

    def _get_widget_data(self, widget, query_params):
        """Get data for a specific widget"""
        organization = widget.dashboard.organization

        # Parse time range
        days = int(query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        if widget.data_source == 'executions':
            return self._get_execution_data(widget, organization, start_date)
        elif widget.data_source == 'workflows':
            return self._get_workflow_data(widget, organization, start_date)
        elif widget.data_source == 'usage':
            return self._get_usage_data(widget, organization, start_date)
        else:
            return {'error': 'Unknown data source'}

    def _get_execution_data(self, widget, organization, start_date):
        """Get execution-related data"""
        queryset = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=start_date
        )

        if widget.widget_type == 'metric':
            if 'total_executions' in widget.query_config:
                return {'value': queryset.count()}
            elif 'success_rate' in widget.query_config:
                total = queryset.count()
                successful = queryset.filter(status='success').count()
                return {'value': (successful / total * 100) if total > 0 else 0}
            elif 'avg_execution_time' in widget.query_config:
                avg_time = queryset.aggregate(avg=Avg('execution_time'))['avg']
                return {'value': avg_time.total_seconds() if avg_time else 0}

        elif widget.widget_type == 'chart':
            # Daily execution trends
            daily_data = []
            for i in range(30):
                date = (timezone.now() - timedelta(days=i)).date()
                day_executions = queryset.filter(started_at__date=date)
                daily_data.append({
                    'date': date.isoformat(),
                    'executions': day_executions.count(),
                    'successful': day_executions.filter(status='success').count(),
                    'failed': day_executions.filter(status='failed').count()
                })
            return {'data': daily_data}

        return {'value': 0}

    def _get_workflow_data(self, widget, organization, start_date):
        """Get workflow-related data"""
        if widget.widget_type == 'metric':
            total_workflows = Workflow.objects.filter(
                organization=organization,
                is_latest_version=True
            ).count()
            return {'value': total_workflows}

        return {'value': 0}

    def _get_usage_data(self, widget, organization, start_date):
        """Get usage analytics data"""
        usage_data = UsageAnalytics.objects.filter(
            organization=organization,
            date__gte=start_date.date()
        ).order_by('-date')

        if widget.widget_type == 'chart':
            data = []
            for usage in usage_data:
                data.append({
                    'date': usage.date.isoformat(),
                    'active_users': usage.active_users,
                    'executions': usage.total_executions,
                    'success_rate': usage.success_rate
                })
            return {'data': data}

        return {'value': 0}


class AnalyticsWidgetViewSet(viewsets.ModelViewSet):
    """
    Analytics widget management
    """
    serializer_class = AnalyticsWidgetSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['widget_type', 'chart_type', 'data_source', 'is_active']
    ordering = ['position_y', 'position_x']

    def get_queryset(self):
        """Get widgets for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AnalyticsWidget.objects.filter(
            dashboard__organization=organization
        ).select_related('dashboard')


class AnalyticsReportViewSet(viewsets.ModelViewSet):
    """
    Analytics report management
    """
    serializer_class = AnalyticsReportSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['report_type', 'delivery_method', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get reports for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AnalyticsReport.objects.filter(
            organization=organization
        ).select_related('organization', 'created_by')

    def perform_create(self, serializer):
        """Create report with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def generate(self, request, pk=None):
        """Generate report immediately"""
        report = self.get_object()

        try:
            # Generate report data
            report_data = self._generate_report_data(report)

            # Update last generated timestamp
            report.last_generated_at = timezone.now()
            report.save()

            return Response({
                'message': 'Report generated successfully',
                'data': report_data
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to generate report: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _generate_report_data(self, report):
        """Generate actual report data"""
        organization = report.organization

        # Get time range based on report type
        if report.report_type == 'daily':
            start_date = timezone.now() - timedelta(days=1)
        elif report.report_type == 'weekly':
            start_date = timezone.now() - timedelta(days=7)
        elif report.report_type == 'monthly':
            start_date = timezone.now() - timedelta(days=30)
        else:
            start_date = timezone.now() - timedelta(days=7)

        # Generate basic metrics
        executions = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=start_date
        )

        total_executions = executions.count()
        successful_executions = executions.filter(status='success').count()
        failed_executions = executions.filter(status='failed').count()

        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

        # Get workflow statistics
        workflows = Workflow.objects.filter(
            organization=organization,
            is_latest_version=True
        )

        return {
            'period': f"{start_date.date()} to {timezone.now().date()}",
            'summary': {
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': failed_executions,
                'success_rate': round(success_rate, 2),
                'total_workflows': workflows.count(),
                'active_workflows': workflows.filter(status='active').count()
            },
            'top_workflows': list(
                executions.values('workflow__name')
                .annotate(execution_count=Count('id'))
                .order_by('-execution_count')[:10]
            )
        }


class AnalyticsMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Analytics metrics (read-only)
    """
    serializer_class = AnalyticsMetricSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['metric_type', 'category', 'aggregation_period']
    ordering = ['-period_start']

    def get_queryset(self):
        """Get metrics for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AnalyticsMetric.objects.filter(
            organization=organization
        ).select_related('organization', 'workflow')


class UsageAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Usage analytics (read-only)
    """
    serializer_class = UsageAnalyticsSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date']
    ordering = ['-date']

    def get_queryset(self):
        """Get usage analytics for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return UsageAnalytics.objects.filter(organization=organization)

    @action(detail=False, methods=['get'])
    def trends(self, request):
        """Get usage trends"""
        organization = request.user.organization_memberships.first().organization
        days = int(request.query_params.get('days', 30))

        start_date = timezone.now().date() - timedelta(days=days)

        usage_data = UsageAnalytics.objects.filter(
            organization=organization,
            date__gte=start_date
        ).order_by('date')

        trends = {
            'dates': [],
            'active_users': [],
            'executions': [],
            'success_rates': [],
            'compute_hours': []
        }

        for usage in usage_data:
            trends['dates'].append(usage.date.isoformat())
            trends['active_users'].append(usage.active_users)
            trends['executions'].append(usage.total_executions)
            trends['success_rates'].append(usage.success_rate)
            trends['compute_hours'].append(usage.total_compute_hours)

        return Response(trends)


class PerformanceMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Performance metrics (read-only)
    """
    serializer_class = PerformanceMetricsSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['workflow']
    ordering = ['-period_start']

    def get_queryset(self):
        """Get performance metrics for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return PerformanceMetrics.objects.filter(
            organization=organization
        ).select_related('organization', 'workflow')


class AnalyticsAlertViewSet(viewsets.ModelViewSet):
    """
    Analytics alert management
    """
    serializer_class = AnalyticsAlertSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['alert_type', 'severity', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get alerts for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return AnalyticsAlert.objects.filter(
            organization=organization
        ).select_related('organization', 'created_by')

    def perform_create(self, serializer):
        """Create alert with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test alert condition"""
        alert = self.get_object()

        try:
            # Evaluate alert condition
            result = self._evaluate_alert_condition(alert)

            return Response({
                'alert_triggered': result['triggered'],
                'current_value': result['value'],
                'threshold': alert.threshold_config,
                'message': result.get('message', '')
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to test alert: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _evaluate_alert_condition(self, alert):
        """Evaluate alert condition"""
        organization = alert.organization

        # Get current metric value
        if alert.metric_name == 'execution_success_rate':
            # Get recent executions
            recent_executions = ExecutionHistory.objects.filter(
                organization=organization,
                started_at__gte=timezone.now() - timedelta(hours=24)
            )

            total = recent_executions.count()
            successful = recent_executions.filter(status='success').count()
            current_value = (successful / total * 100) if total > 0 else 100

            # Check threshold
            threshold = alert.threshold_config.get('value', 95)
            operator = alert.threshold_config.get('operator', 'less_than')

            if operator == 'less_than':
                triggered = current_value < threshold
            else:
                triggered = current_value > threshold

            return {
                'triggered': triggered,
                'value': current_value,
                'message': f'Success rate is {current_value:.1f}%'
            }

        return {'triggered': False, 'value': 0}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overview_stats(request):
    """
    Get overview analytics statistics
    """
    organization = request.user.organization_memberships.first().organization

    # Get time range
    days = int(request.query_params.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Execution statistics
    executions = ExecutionHistory.objects.filter(
        organization=organization,
        started_at__gte=start_date
    )

    total_executions = executions.count()
    successful_executions = executions.filter(status='success').count()
    failed_executions = executions.filter(status='failed').count()

    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

    # Workflow statistics
    workflows = Workflow.objects.filter(
        organization=organization,
        is_latest_version=True
    )

    active_workflows = workflows.filter(status='active').count()

    # User statistics
    from apps.organizations.models import OrganizationMember
    active_members = OrganizationMember.objects.filter(
        organization=organization,
        status='active'
    ).count()

    # Recent trends (last 7 days vs previous 7 days)
    current_week = timezone.now() - timedelta(days=7)
    previous_week = timezone.now() - timedelta(days=14)

    current_week_executions = ExecutionHistory.objects.filter(
        organization=organization,
        started_at__gte=current_week
    ).count()

    previous_week_executions = ExecutionHistory.objects.filter(
        organization=organization,
        started_at__gte=previous_week,
        started_at__lt=current_week
    ).count()

    execution_trend = 0
    if previous_week_executions > 0:
        execution_trend = ((current_week_executions - previous_week_executions) / previous_week_executions) * 100

    return Response({
        'period_days': days,
        'total_executions': total_executions,
        'successful_executions': successful_executions,
        'failed_executions': failed_executions,
        'success_rate': round(success_rate, 2),
        'total_workflows': workflows.count(),
        'active_workflows': active_workflows,
        'active_members': active_members,
        'execution_trend': round(execution_trend, 1),
        'avg_execution_time': executions.aggregate(
            avg=Avg('execution_time')
        )['avg']
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workflow_analytics(request, workflow_id):
    """
    Get analytics for a specific workflow
    """
    organization = request.user.organization_memberships.first().organization

    try:
        workflow = Workflow.objects.get(
            id=workflow_id,
            organization=organization
        )
    except Workflow.DoesNotExist:
        return Response(
            {'error': 'Workflow not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get time range
    days = int(request.query_params.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Execution statistics for this workflow
    executions = ExecutionHistory.objects.filter(
        workflow=workflow,
        started_at__gte=start_date
    )

    total_executions = executions.count()
    successful_executions = executions.filter(status='success').count()
    failed_executions = executions.filter(status='failed').count()

    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

    # Daily execution trends
    daily_trends = []
    for i in range(days):
        date = (timezone.now() - timedelta(days=i)).date()
        day_executions = executions.filter(started_at__date=date)

        daily_trends.append({
            'date': date.isoformat(),
            'total': day_executions.count(),
            'successful': day_executions.filter(status='success').count(),
            'failed': day_executions.filter(status='failed').count()
        })

    # Performance metrics
    avg_execution_time = executions.aggregate(avg=Avg('execution_time'))['avg']

    return Response({
        'workflow': {
            'id': workflow.id,
            'name': workflow.name,
            'status': workflow.status
        },
        'period_days': days,
        'total_executions': total_executions,
        'successful_executions': successful_executions,
        'failed_executions': failed_executions,
        'success_rate': round(success_rate, 2),
        'avg_execution_time': avg_execution_time,
        'daily_trends': daily_trends
    })