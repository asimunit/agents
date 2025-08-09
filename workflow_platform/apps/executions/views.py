"""
Executions Views - Workflow execution management and monitoring
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
import uuid

from .models import (
    ExecutionQueue, ExecutionHistory, ExecutionAlert,
    ExecutionResource, ExecutionSchedule
)
from .serializers import (
    ExecutionQueueSerializer, ExecutionHistorySerializer,
    ExecutionAlertSerializer, ExecutionResourceSerializer,
    ExecutionScheduleSerializer, ExecutionStatsSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.workflows.models import Workflow


class ExecutionQueueViewSet(viewsets.ModelViewSet):
    """
    Execution queue management
    """
    serializer_class = ExecutionQueueSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'priority', 'trigger_type', 'workflow']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get execution queue for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ExecutionQueue.objects.filter(
            workflow__organization=organization
        ).select_related('workflow', 'triggered_by')

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry a failed execution"""
        execution = self.get_object()

        if not execution.can_retry():
            return Response(
                {'error': 'Execution cannot be retried'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Reset execution for retry
        execution.status = 'pending'
        execution.error_message = ''
        execution.error_details = {}
        execution.scheduled_at = timezone.now()
        execution.save()

        return Response({'message': 'Execution queued for retry'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending execution"""
        execution = self.get_object()

        if execution.status not in ['pending', 'running']:
            return Response(
                {'error': 'Cannot cancel execution in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        execution.status = 'cancelled'
        execution.completed_at = timezone.now()
        execution.save()

        return Response({'message': 'Execution cancelled'})

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get execution queue statistics"""
        organization = request.user.organization_memberships.first().organization

        queryset = ExecutionQueue.objects.filter(
            workflow__organization=organization
        )

        stats = {
            'total': queryset.count(),
            'pending': queryset.filter(status='pending').count(),
            'running': queryset.filter(status='running').count(),
            'completed': queryset.filter(status='completed').count(),
            'failed': queryset.filter(status='failed').count(),
            'cancelled': queryset.filter(status='cancelled').count(),
        }

        return Response(stats)


class ExecutionHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Execution history for analytics and monitoring
    """
    serializer_class = ExecutionHistorySerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'trigger_type', 'workflow']
    ordering = ['-started_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get execution history for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ExecutionHistory.objects.filter(
            organization=organization
        ).select_related('workflow', 'triggered_by')

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Get execution analytics"""
        organization = request.user.organization_memberships.first().organization

        # Get date range from query params
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        queryset = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=start_date
        )

        # Overall statistics
        total_executions = queryset.count()
        successful_executions = queryset.filter(status='success').count()
        failed_executions = queryset.filter(status='failed').count()

        success_rate = 0
        if total_executions > 0:
            success_rate = (successful_executions / total_executions) * 100

        # Average execution time
        avg_execution_time = queryset.aggregate(
            avg_time=Avg('execution_time')
        )['avg_time']

        # Execution trends (daily)
        daily_stats = []
        for i in range(days):
            date = (timezone.now() - timedelta(days=i)).date()
            day_executions = queryset.filter(started_at__date=date)

            daily_stats.append({
                'date': date,
                'total': day_executions.count(),
                'successful': day_executions.filter(status='success').count(),
                'failed': day_executions.filter(status='failed').count(),
            })

        # Top workflows by execution count
        top_workflows = queryset.values(
            'workflow__name', 'workflow__id'
        ).annotate(
            execution_count=Count('id'),
            success_count=Count('id', filter=Q(status='success')),
            avg_duration=Avg('execution_time')
        ).order_by('-execution_count')[:10]

        return Response({
            'period_days': days,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': round(success_rate, 2),
            'average_execution_time': avg_execution_time,
            'daily_trends': daily_stats,
            'top_workflows': list(top_workflows)
        })

    @action(detail=False, methods=['get'])
    def performance(self, request):
        """Get performance metrics"""
        organization = request.user.organization_memberships.first().organization

        # Get recent executions for performance analysis
        recent_executions = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=timezone.now() - timedelta(days=7)
        )

        # Performance metrics
        avg_execution_time = recent_executions.aggregate(
            avg_time=Avg('execution_time')
        )['avg_time']

        avg_nodes_executed = recent_executions.aggregate(
            avg_nodes=Avg('nodes_executed')
        )['avg_nodes']

        avg_memory_usage = recent_executions.aggregate(
            avg_memory=Avg('memory_peak_mb')
        )['avg_memory']

        # Performance trends
        performance_trends = []
        for i in range(7):
            date = (timezone.now() - timedelta(days=i)).date()
            day_executions = recent_executions.filter(started_at__date=date)

            if day_executions.exists():
                avg_time = day_executions.aggregate(avg=Avg('execution_time'))['avg']
                avg_memory = day_executions.aggregate(avg=Avg('memory_peak_mb'))['avg']

                performance_trends.append({
                    'date': date,
                    'avg_execution_time': avg_time,
                    'avg_memory_usage': avg_memory,
                    'execution_count': day_executions.count()
                })

        return Response({
            'average_execution_time': avg_execution_time,
            'average_nodes_executed': avg_nodes_executed,
            'average_memory_usage': avg_memory_usage,
            'performance_trends': performance_trends
        })


class ExecutionAlertViewSet(viewsets.ModelViewSet):
    """
    Execution alert management
    """
    serializer_class = ExecutionAlertSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['alert_type', 'severity', 'status', 'workflow']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get alerts for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ExecutionAlert.objects.filter(
            organization=organization
        ).select_related('workflow', 'acknowledged_by')

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert"""
        alert = self.get_object()
        alert.acknowledge(request.user)

        return Response({'message': 'Alert acknowledged'})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        alert.resolve()

        return Response({'message': 'Alert resolved'})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get alert summary"""
        organization = request.user.organization_memberships.first().organization

        queryset = ExecutionAlert.objects.filter(organization=organization)

        summary = {
            'total': queryset.count(),
            'active': queryset.filter(status='active').count(),
            'acknowledged': queryset.filter(status='acknowledged').count(),
            'resolved': queryset.filter(status='resolved').count(),
            'by_severity': {
                'critical': queryset.filter(severity='critical').count(),
                'high': queryset.filter(severity='high').count(),
                'medium': queryset.filter(severity='medium').count(),
                'low': queryset.filter(severity='low').count(),
            },
            'by_type': {}
        }

        # Count by alert type
        for alert_type, _ in ExecutionAlert.ALERT_TYPES:
            summary['by_type'][alert_type] = queryset.filter(
                alert_type=alert_type
            ).count()

        return Response(summary)


class ExecutionResourceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Execution resource usage tracking
    """
    serializer_class = ExecutionResourceSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['organization']
    ordering = ['-start_time']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get resource usage for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ExecutionResource.objects.filter(organization=organization)

    @action(detail=False, methods=['get'])
    def usage_summary(self, request):
        """Get resource usage summary"""
        organization = request.user.organization_memberships.first().organization

        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        queryset = ExecutionResource.objects.filter(
            organization=organization,
            start_time__gte=start_date
        )

        # Calculate totals
        total_cpu_hours = sum(res.cpu_seconds for res in queryset) / 3600
        total_memory_gb_hours = sum(res.memory_mb_seconds for res in queryset) / (1024 * 3600)
        total_storage_gb = sum(res.storage_mb for res in queryset) / 1024
        total_network_gb = sum(res.network_bytes for res in queryset) / (1024 ** 3)

        # Daily breakdown
        daily_usage = []
        for i in range(days):
            date = (timezone.now() - timedelta(days=i)).date()
            day_resources = queryset.filter(start_time__date=date)

            daily_usage.append({
                'date': date,
                'cpu_hours': sum(res.cpu_seconds for res in day_resources) / 3600,
                'memory_gb_hours': sum(res.memory_mb_seconds for res in day_resources) / (1024 * 3600),
                'executions': day_resources.count()
            })

        return Response({
            'period_days': days,
            'total_cpu_hours': round(total_cpu_hours, 2),
            'total_memory_gb_hours': round(total_memory_gb_hours, 2),
            'total_storage_gb': round(total_storage_gb, 2),
            'total_network_gb': round(total_network_gb, 2),
            'daily_usage': daily_usage
        })


class ExecutionScheduleViewSet(viewsets.ModelViewSet):
    """
    Execution schedule management
    """
    serializer_class = ExecutionScheduleSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'workflow']
    ordering = ['next_run_time']

    def get_queryset(self):
        """Get schedules for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return ExecutionSchedule.objects.filter(
            workflow__organization=organization
        ).select_related('workflow')

    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        """Enable a schedule"""
        schedule = self.get_object()
        schedule.status = 'active'
        schedule.save()

        return Response({'message': 'Schedule enabled'})

    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        """Disable a schedule"""
        schedule = self.get_object()
        schedule.status = 'disabled'
        schedule.save()

        return Response({'message': 'Schedule disabled'})

    @action(detail=True, methods=['post'])
    def trigger_now(self, request, pk=None):
        """Trigger scheduled workflow immediately"""
        schedule = self.get_object()

        # Create execution queue entry
        execution = ExecutionQueue.objects.create(
            workflow=schedule.workflow,
            execution_id=f"manual-{uuid.uuid4().hex[:8]}",
            trigger_type='manual',
            triggered_by=request.user,
            priority='high'
        )

        return Response({
            'message': 'Workflow triggered',
            'execution_id': execution.execution_id
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_workflow(request, workflow_id):
    """
    Trigger a workflow execution
    """
    try:
        workflow = Workflow.objects.get(
            id=workflow_id,
            organization=request.user.organization_memberships.first().organization
        )
    except Workflow.DoesNotExist:
        return Response(
            {'error': 'Workflow not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get input data from request
    input_data = request.data.get('input_data', {})
    variables = request.data.get('variables', {})
    priority = request.data.get('priority', 'normal')

    # Create execution queue entry
    execution = ExecutionQueue.objects.create(
        workflow=workflow,
        execution_id=f"api-{uuid.uuid4().hex[:8]}",
        trigger_type='api',
        triggered_by=request.user,
        input_data=input_data,
        variables=variables,
        priority=priority
    )

    return Response({
        'message': 'Workflow execution queued',
        'execution_id': execution.execution_id,
        'status': execution.status
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def execution_status(request, execution_id):
    """
    Get execution status
    """
    organization = request.user.organization_memberships.first().organization

    try:
        # Try queue first
        execution = ExecutionQueue.objects.get(
            execution_id=execution_id,
            workflow__organization=organization
        )

        return Response({
            'execution_id': execution.execution_id,
            'status': execution.status,
            'created_at': execution.created_at,
            'started_at': execution.started_at,
            'completed_at': execution.completed_at,
            'error_message': execution.error_message
        })

    except ExecutionQueue.DoesNotExist:
        # Try history
        try:
            execution = ExecutionHistory.objects.get(
                execution_id=execution_id,
                organization=organization
            )

            return Response({
                'execution_id': execution.execution_id,
                'status': execution.status,
                'started_at': execution.started_at,
                'completed_at': execution.completed_at,
                'execution_time': execution.execution_time,
                'error_message': execution.error_message
            })

        except ExecutionHistory.DoesNotExist:
            return Response(
                {'error': 'Execution not found'},
                status=status.HTTP_404_NOT_FOUND
            )