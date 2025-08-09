"""
Workflow API Views - Comprehensive REST API that outperforms N8n
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
import asyncio

from .models import Workflow, WorkflowExecution, WorkflowTemplate, WorkflowComment
from .serializers import (
    WorkflowSerializer, WorkflowDetailSerializer, WorkflowExecutionSerializer,
    WorkflowTemplateSerializer, WorkflowCommentSerializer, WorkflowCreateSerializer
)
from apps.core.workflow_engine import workflow_engine
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.core.exceptions import WorkflowExecutionError


class WorkflowViewSet(viewsets.ModelViewSet):
    """
    Advanced Workflow API with comprehensive features
    """
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'trigger_type', 'category', 'is_template']
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['created_at', 'updated_at', 'name', 'total_executions', 'success_rate']
    ordering = ['-updated_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get workflows for current organization"""
        return Workflow.objects.filter(
            organization=self.request.user.organization_memberships.first().organization
        ).select_related('category', 'created_by', 'updated_by').prefetch_related('executions')

    def get_serializer_class(self):
        """Dynamic serializer based on action"""
        if self.action == 'create':
            return WorkflowCreateSerializer
        elif self.action == 'retrieve':
            return WorkflowDetailSerializer
        return WorkflowSerializer

    def perform_create(self, serializer):
        """Create workflow with organization and user context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user,
            updated_by=self.request.user
        )

    def perform_update(self, serializer):
        """Update workflow with user context"""
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute workflow manually"""
        workflow = self.get_object()

        # Check if workflow is active
        if workflow.status != 'active':
            return Response(
                {'error': 'Workflow must be active to execute'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get input data from request
        input_data = request.data.get('input_data', {})

        try:
            # Execute workflow asynchronously
            execution = asyncio.run(
                workflow_engine.execute_workflow(
                    workflow=workflow,
                    input_data=input_data,
                    triggered_by_user_id=request.user.id,
                    trigger_source='manual'
                )
            )

            serializer = WorkflowExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except WorkflowExecutionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Execution failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """Get workflow executions with filtering"""
        workflow = self.get_object()

        # Filter executions
        executions = workflow.executions.all()

        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            executions = executions.filter(status=status_filter)

        days = request.query_params.get('days', 30)
        if days:
            cutoff_date = timezone.now() - timedelta(days=int(days))
            executions = executions.filter(started_at__gte=cutoff_date)

        # Paginate
        page = self.paginate_queryset(executions.order_by('-started_at'))
        if page is not None:
            serializer = WorkflowExecutionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = WorkflowExecutionSerializer(executions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate workflow"""
        original_workflow = self.get_object()

        # Create copy
        new_name = request.data.get('name', f"{original_workflow.name} (Copy)")

        duplicated_workflow = Workflow.objects.create(
            organization=original_workflow.organization,
            name=new_name,
            description=original_workflow.description,
            category=original_workflow.category,
            nodes=original_workflow.nodes.copy(),
            connections=original_workflow.connections.copy(),
            variables=original_workflow.variables.copy(),
            trigger_type=original_workflow.trigger_type,
            execution_timeout=original_workflow.execution_timeout,
            max_retries=original_workflow.max_retries,
            retry_delay=original_workflow.retry_delay,
            parallel_execution=original_workflow.parallel_execution,
            settings=original_workflow.settings.copy(),
            error_handling=original_workflow.error_handling.copy(),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        serializer = WorkflowDetailSerializer(duplicated_workflow)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def create_version(self, request, pk=None):
        """Create new version of workflow"""
        workflow = self.get_object()

        new_version = workflow.create_version(request.user)

        serializer = WorkflowDetailSerializer(new_version)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """Get all versions of workflow"""
        workflow = self.get_object()

        # Get all versions (including parent and children)
        parent = workflow.parent_workflow or workflow
        versions = Workflow.objects.filter(
            Q(id=parent.id) | Q(parent_workflow=parent)
        ).order_by('-version')

        serializer = WorkflowSerializer(versions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate workflow"""
        workflow = self.get_object()

        # Validate workflow before activation
        validation_errors = workflow.validate_workflow()
        if validation_errors:
            return Response(
                {'error': 'Workflow validation failed', 'details': validation_errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        workflow.status = 'active'
        workflow.save()

        return Response({'message': 'Workflow activated successfully'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate workflow"""
        workflow = self.get_object()
        workflow.status = 'inactive'
        workflow.save()

        return Response({'message': 'Workflow deactivated successfully'})

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get workflow analytics"""
        workflow = self.get_object()

        # Date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Get executions in date range
        executions = workflow.executions.filter(started_at__gte=start_date)

        # Basic metrics
        total_executions = executions.count()
        successful_executions = executions.filter(status='completed').count()
        failed_executions = executions.filter(status='failed').count()

        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

        # Average execution time
        avg_execution_time = executions.filter(
            status='completed',
            execution_time__isnull=False
        ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

        # Daily execution counts
        daily_stats = []
        for i in range(days):
            date = (timezone.now() - timedelta(days=i)).date()
            day_executions = executions.filter(started_at__date=date)

            daily_stats.append({
                'date': date.isoformat(),
                'total': day_executions.count(),
                'successful': day_executions.filter(status='completed').count(),
                'failed': day_executions.filter(status='failed').count(),
            })

        # Node performance
        from apps.nodes.models import NodeExecutionLog
        node_stats = NodeExecutionLog.objects.filter(
            execution__workflow=workflow,
            started_at__gte=start_date
        ).values('node_type__name').annotate(
            total_executions=Count('id'),
            avg_execution_time=Avg('execution_time'),
            failure_rate=Count('id', filter=Q(status='failed')) * 100.0 / Count('id')
        ).order_by('-total_executions')[:10]

        # Error analysis
        error_types = NodeExecutionLog.objects.filter(
            execution__workflow=workflow,
            started_at__gte=start_date,
            status='failed'
        ).values('error_type').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        analytics_data = {
            'overview': {
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': failed_executions,
                'success_rate': round(success_rate, 2),
                'average_execution_time': round(avg_execution_time, 2) if avg_execution_time else 0,
            },
            'daily_stats': daily_stats,
            'node_performance': list(node_stats),
            'error_analysis': list(error_types),
            'performance_trends': {
                'execution_time_trend': self._get_execution_time_trend(workflow, start_date),
                'success_rate_trend': self._get_success_rate_trend(workflow, start_date),
            }
        }

        return Response(analytics_data)

    def _get_execution_time_trend(self, workflow, start_date):
        """Get execution time trend data"""
        # Implementation for execution time trend analysis
        # This would calculate daily average execution times
        return []

    def _get_success_rate_trend(self, workflow, start_date):
        """Get success rate trend data"""
        # Implementation for success rate trend analysis
        # This would calculate daily success rates
        return []

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share workflow with users"""
        workflow = self.get_object()

        from apps.workflows.models import WorkflowShare
        from django.contrib.auth.models import User

        user_ids = request.data.get('user_ids', [])
        permission = request.data.get('permission', 'view')

        shares_created = []
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                share, created = WorkflowShare.objects.get_or_create(
                    workflow=workflow,
                    shared_with=user,
                    defaults={
                        'permission': permission,
                        'shared_by': request.user
                    }
                )
                if created:
                    shares_created.append(share)
            except User.DoesNotExist:
                continue

        return Response({
            'message': f'Workflow shared with {len(shares_created)} users',
            'shares_created': len(shares_created)
        })

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        """Get or create workflow comments"""
        workflow = self.get_object()

        if request.method == 'GET':
            comments = workflow.comments.filter(parent_comment__isnull=True).order_by('-created_at')
            serializer = WorkflowCommentSerializer(comments, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            serializer = WorkflowCommentSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(
                    workflow=workflow,
                    author=request.user
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get organization workflow statistics"""
        organization = request.user.organization_memberships.first().organization
        workflows = self.get_queryset()

        # Basic counts
        total_workflows = workflows.count()
        active_workflows = workflows.filter(status='active').count()

        # Execution statistics
        total_executions = WorkflowExecution.objects.filter(
            workflow__organization=organization
        ).count()

        recent_executions = WorkflowExecution.objects.filter(
            workflow__organization=organization,
            started_at__gte=timezone.now() - timedelta(days=30)
        )

        successful_recent = recent_executions.filter(status='completed').count()
        total_recent = recent_executions.count()
        recent_success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0

        # Most used workflows
        popular_workflows = workflows.annotate(
            execution_count=Count('executions')
        ).order_by('-execution_count')[:5]

        statistics = {
            'totals': {
                'workflows': total_workflows,
                'active_workflows': active_workflows,
                'total_executions': total_executions,
            },
            'recent_performance': {
                'executions_last_30_days': total_recent,
                'success_rate_last_30_days': round(recent_success_rate, 2),
            },
            'popular_workflows': [
                {
                    'id': wf.id,
                    'name': wf.name,
                    'execution_count': wf.execution_count
                }
                for wf in popular_workflows
            ]
        }

        return Response(statistics)


class WorkflowExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Workflow Execution API with monitoring and control
    """
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'trigger_source']
    ordering_fields = ['started_at', 'completed_at', 'execution_time']
    ordering = ['-started_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get executions for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return WorkflowExecution.objects.filter(
            workflow__organization=organization
        ).select_related('workflow', 'triggered_by')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel running execution"""
        execution = self.get_object()

        if execution.status not in ['pending', 'running']:
            return Response(
                {'error': 'Can only cancel pending or running executions'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Cancel execution
        success = asyncio.run(workflow_engine.cancel_execution(str(execution.id)))

        if success:
            return Response({'message': 'Execution cancelled successfully'})
        else:
            return Response(
                {'error': 'Failed to cancel execution'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Get detailed execution logs"""
        execution = self.get_object()

        from apps.nodes.models import NodeExecutionLog
        logs = execution.node_logs.all().order_by('started_at')

        log_data = []
        for log in logs:
            log_data.append({
                'id': log.id,
                'node_id': log.node_id,
                'node_name': log.node_name,
                'node_type': log.node_type.name if log.node_type else 'unknown',
                'status': log.status,
                'started_at': log.started_at,
                'completed_at': log.completed_at,
                'execution_time': log.execution_time,
                'error_message': log.error_message,
                'retry_count': log.retry_count,
            })

        return Response({
            'execution_id': execution.id,
            'logs': log_data
        })

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry failed execution"""
        execution = self.get_object()

        if execution.status != 'failed':
            return Response(
                {'error': 'Can only retry failed executions'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Create new execution as retry
            new_execution = asyncio.run(
                workflow_engine.execute_workflow(
                    workflow=execution.workflow,
                    input_data=execution.input_data,
                    triggered_by_user_id=request.user.id,
                    trigger_source='retry'
                )
            )

            # Link to original execution
            new_execution.parent_execution = execution
            new_execution.save()

            serializer = WorkflowExecutionSerializer(new_execution)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Retry failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WorkflowTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Workflow Template API for marketplace
    """
    serializer_class = WorkflowTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['difficulty', 'industry', 'is_featured', 'is_official']
    search_fields = ['title', 'short_description', 'long_description', 'use_case']
    ordering_fields = ['usage_count', 'rating', 'published_at']
    ordering = ['-is_featured', '-rating', '-usage_count']

    def get_queryset(self):
        """Get published templates"""
        return WorkflowTemplate.objects.filter(
            published_at__isnull=False
        ).select_related('workflow')

    @action(detail=True, methods=['post'])
    def use_template(self, request, pk=None):
        """Create workflow from template"""
        template = self.get_object()
        organization = request.user.organization_memberships.first().organization

        # Check if user's plan supports this template
        org_plan_priority = {
            'free': 0, 'pro': 1, 'business': 2, 'enterprise': 3
        }
        template_plan_priority = org_plan_priority.get(template.required_plan, 0)
        user_plan_priority = org_plan_priority.get(organization.plan, 0)

        if template_plan_priority > user_plan_priority:
            return Response(
                {'error': f'Template requires {template.required_plan} plan or higher'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create workflow from template
        workflow_name = request.data.get('name', template.title)

        new_workflow = Workflow.objects.create(
            organization=organization,
            name=workflow_name,
            description=template.short_description,
            nodes=template.workflow.nodes.copy(),
            connections=template.workflow.connections.copy(),
            variables=template.workflow.variables.copy(),
            trigger_type=template.workflow.trigger_type,
            execution_timeout=template.workflow.execution_timeout,
            max_retries=template.workflow.max_retries,
            retry_delay=template.workflow.retry_delay,
            parallel_execution=template.workflow.parallel_execution,
            settings=template.workflow.settings.copy(),
            error_handling=template.workflow.error_handling.copy(),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        # Increment template usage
        template.usage_count += 1
        template.save(update_fields=['usage_count'])

        serializer = WorkflowDetailSerializer(new_workflow)
        return Response(serializer.data, status=status.HTTP_201_CREATED)