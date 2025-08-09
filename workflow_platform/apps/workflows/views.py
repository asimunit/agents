"""
Workflows Views - Complete workflow management API
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import json
import uuid
import logging

from .models import (
    Workflow, WorkflowExecution, WorkflowTemplate,
    WorkflowComment, WorkflowShare, WorkflowCategory
)
from .serializers import (
    WorkflowSerializer, WorkflowCreateSerializer, WorkflowDetailSerializer,
    WorkflowExecutionSerializer, WorkflowTemplateSerializer,
    WorkflowCommentSerializer, WorkflowShareSerializer,
    WorkflowCategorySerializer, WorkflowStatsSerializer,
    WorkflowExportSerializer, WorkflowImportSerializer,
    WorkflowAnalyticsSerializer, WorkflowCloneSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.executions.models import ExecutionQueue

logger = logging.getLogger(__name__)


class WorkflowViewSet(viewsets.ModelViewSet):
    """
    Complete workflow management API
    """
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'trigger_type', 'category', 'is_template', 'is_public']
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['created_at', 'updated_at', 'name', 'total_executions', 'success_rate']
    ordering = ['-updated_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get workflows for current organization"""
        organization = self.request.user.organization_memberships.first().organization

        # Base queryset - workflows in organization
        queryset = Workflow.objects.filter(
            organization=organization,
            is_latest_version=True
        ).select_related('category', 'created_by', 'updated_by')

        # Add workflows shared with user
        shared_workflows = Workflow.objects.filter(
            shares__shared_with=self.request.user
        ).select_related('category', 'created_by', 'updated_by')

        # Add public workflows
        public_workflows = Workflow.objects.filter(
            is_public=True,
            is_latest_version=True
        ).select_related('category', 'created_by', 'updated_by')

        # Combine querysets
        all_workflow_ids = set()
        for qs in [queryset, shared_workflows, public_workflows]:
            all_workflow_ids.update(qs.values_list('id', flat=True))

        return Workflow.objects.filter(id__in=all_workflow_ids).distinct()

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
        """Update workflow with version management"""
        instance = serializer.instance

        # Check if this is a major change that requires versioning
        if self._requires_new_version(instance, serializer.validated_data):
            # Create new version
            old_version = instance.version
            instance.is_latest_version = False
            instance.save()

            # Create new version
            new_version = f"{float(old_version) + 0.1:.1f}"
            serializer.save(
                version=new_version,
                is_latest_version=True,
                updated_by=self.request.user
            )
        else:
            # Minor update
            serializer.save(updated_by=self.request.user)

    def _requires_new_version(self, instance, validated_data):
        """Check if changes require a new version"""
        major_fields = ['nodes', 'connections', 'trigger_type']

        for field in major_fields:
            if field in validated_data and getattr(instance, field) != validated_data[field]:
                return True
        return False

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute workflow with input data"""
        workflow = self.get_object()

        # Check if workflow is active
        if workflow.status != 'active':
            return Response(
                {'error': 'Workflow is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get input data
        input_data = request.data.get('input_data', {})
        variables = request.data.get('variables', {})
        priority = request.data.get('priority', 'normal')

        try:
            # Create execution queue entry
            execution = ExecutionQueue.objects.create(
                workflow=workflow,
                execution_id=f"manual-{uuid.uuid4().hex[:8]}",
                trigger_type='manual',
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

        except Exception as e:
            logger.error(f"Error executing workflow {workflow.id}: {str(e)}")
            return Response(
                {'error': f'Failed to execute workflow: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Create a copy of the workflow"""
        original_workflow = self.get_object()

        # Create duplicate
        workflow_copy = Workflow.objects.create(
            organization=original_workflow.organization,
            name=f"{original_workflow.name} (Copy)",
            description=f"Copy of {original_workflow.name}",
            category=original_workflow.category,
            nodes=original_workflow.nodes.copy(),
            connections=original_workflow.connections.copy(),
            variables=original_workflow.variables.copy(),
            trigger_type=original_workflow.trigger_type,
            tags=original_workflow.tags.copy(),
            settings=original_workflow.settings.copy(),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        serializer = WorkflowSerializer(workflow_copy)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """Get all versions of the workflow"""
        workflow = self.get_object()

        # Get all versions (same name and organization)
        versions = Workflow.objects.filter(
            organization=workflow.organization,
            name=workflow.name
        ).order_by('-created_at')

        serializer = WorkflowSerializer(versions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate workflow"""
        workflow = self.get_object()

        # Validate workflow before activation
        validation_errors = self._validate_workflow(workflow)
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

        # Cancel any pending executions
        ExecutionQueue.objects.filter(
            workflow=workflow,
            status='pending'
        ).update(status='cancelled')

        return Response({'message': 'Workflow deactivated successfully'})

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share workflow with other users"""
        workflow = self.get_object()
        user_ids = request.data.get('user_ids', [])
        permission = request.data.get('permission', 'view')

        # Validate permission
        if permission not in ['view', 'edit', 'execute', 'admin']:
            return Response(
                {'error': 'Invalid permission'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user has permission to share
        if workflow.created_by != request.user:
            member = request.user.organization_memberships.filter(
                organization=workflow.organization
            ).first()
            if not member or member.role not in ['owner', 'admin']:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Create shares
        from django.contrib.auth.models import User
        users = User.objects.filter(id__in=user_ids)

        for user in users:
            WorkflowShare.objects.update_or_create(
                workflow=workflow,
                shared_with=user,
                defaults={
                    'permission': permission,
                    'shared_by': request.user
                }
            )

        return Response({
            'message': f'Workflow shared with {len(users)} users',
            'shared_with': [{'id': u.id, 'username': u.username} for u in users]
        })

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get workflow analytics"""
        workflow = self.get_object()

        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Get executions
        executions = WorkflowExecution.objects.filter(
            workflow=workflow,
            started_at__gte=start_date
        )

        # Calculate metrics
        total_executions = executions.count()
        successful_executions = executions.filter(status='success').count()
        failed_executions = executions.filter(status='failed').count()

        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

        # Daily trends
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
            'metrics': {
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': failed_executions,
                'success_rate': round(success_rate, 2),
                'avg_execution_time': avg_execution_time
            },
            'daily_trends': daily_trends
        })

    def _validate_workflow(self, workflow):
        """Validate workflow configuration"""
        errors = []

        # Check if workflow has nodes
        if not workflow.nodes:
            errors.append("Workflow must have at least one node")

        # Check for orphaned nodes
        node_ids = set(node.get('id') for node in workflow.nodes)
        connected_nodes = set()

        for connection in workflow.connections:
            connected_nodes.add(connection.get('source'))
            connected_nodes.add(connection.get('target'))

        # Check for trigger node
        has_trigger = any(
            node.get('type') == 'trigger' for node in workflow.nodes
        )

        if not has_trigger and workflow.trigger_type != 'manual':
            errors.append("Workflow must have a trigger node for non-manual triggers")

        return errors


class WorkflowExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Workflow execution monitoring and control
    """
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'trigger_source', 'workflow']
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

        # Update execution status
        execution.status = 'cancelled'
        execution.completed_at = timezone.now()
        execution.save()

        return Response({'message': 'Execution cancelled successfully'})

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Get detailed execution logs"""
        execution = self.get_object()

        from apps.nodes.models import NodeExecutionLog
        logs = NodeExecutionLog.objects.filter(
            workflow_execution=execution
        ).order_by('started_at')

        log_data = []
        for log in logs:
            log_data.append({
                'id': log.id,
                'node_id': log.node_id,
                'node_type': log.node_type,
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
            # Create new execution queue entry
            new_execution = ExecutionQueue.objects.create(
                workflow=execution.workflow,
                execution_id=f"retry-{uuid.uuid4().hex[:8]}",
                trigger_type='retry',
                triggered_by=request.user,
                input_data=getattr(execution, 'input_data', {}),
                variables=getattr(execution, 'variables', {}),
                priority='high'
            )

            return Response({
                'message': 'Execution retry queued',
                'execution_id': new_execution.execution_id
            }, status=status.HTTP_201_CREATED)

            return Response({
                'message': 'Execution retry queued',
                'execution_id': new_execution.execution_id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Retry failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WorkflowTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Workflow template marketplace
    """
    serializer_class = WorkflowTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_featured']
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['created_at', 'use_count', 'rating']
    ordering = ['-is_featured', '-rating', '-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get all available templates"""
        return WorkflowTemplate.objects.filter(
            is_active=True
        ).select_related('category', 'created_by')

    @action(detail=True, methods=['post'])
    def use(self, request, pk=None):
        """Create workflow from template"""
        template = self.get_object()
        organization = request.user.organization_memberships.first().organization

        # Get custom values from request
        name = request.data.get('name', template.name)
        description = request.data.get('description', template.description)
        variables = request.data.get('variables', template.default_variables)

        try:
            # Create workflow from template
            workflow = Workflow.objects.create(
                organization=organization,
                name=name,
                description=description,
                category=template.category,
                nodes=template.workflow_data.get('nodes', []),
                connections=template.workflow_data.get('connections', []),
                variables=variables,
                trigger_type=template.workflow_data.get('trigger_type', 'manual'),
                tags=template.tags.copy(),
                created_by=request.user,
                updated_by=request.user,
                status='draft'
            )

            # Increment template usage count
            template.use_count += 1
            template.save()

            serializer = WorkflowSerializer(workflow)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Failed to create workflow from template: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WorkflowCommentViewSet(viewsets.ModelViewSet):
    """
    Workflow collaboration comments
    """
    serializer_class = WorkflowCommentSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['workflow', 'node_id']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get comments for accessible workflows"""
        organization = self.request.user.organization_memberships.first().organization
        return WorkflowComment.objects.filter(
            workflow__organization=organization
        ).select_related('workflow', 'author')

    def perform_create(self, serializer):
        """Create comment with author"""
        serializer.save(author=self.request.user)


class WorkflowShareViewSet(viewsets.ModelViewSet):
    """
    Workflow sharing management
    """
    serializer_class = WorkflowShareSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['workflow', 'permission']

    def get_queryset(self):
        """Get shares for workflows user owns or can manage"""
        user = self.request.user
        organization = user.organization_memberships.first().organization

        # Get workflows user can manage shares for
        manageable_workflows = Workflow.objects.filter(
            Q(organization=organization, created_by=user) |
            Q(organization=organization, shares__shared_with=user, shares__permission='admin')
        )

        return WorkflowShare.objects.filter(
            workflow__in=manageable_workflows
        ).select_related('workflow', 'shared_with', 'shared_by')

    def perform_create(self, serializer):
        """Create share with current user as sharer"""
        serializer.save(shared_by=self.request.user)


class WorkflowCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Workflow categories
    """
    serializer_class = WorkflowCategorySerializer
    permission_classes = [IsAuthenticated]
    ordering = ['name']

    def get_queryset(self):
        """Get all workflow categories"""
        return WorkflowCategory.objects.all()


# Function-based views for custom endpoints

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workflow_stats(request):
    """
    Get overall workflow statistics for organization
    """
    organization = request.user.organization_memberships.first().organization

    # Get date range
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Calculate statistics
    workflows = Workflow.objects.filter(
        organization=organization,
        is_latest_version=True
    )

    executions = WorkflowExecution.objects.filter(
        workflow__organization=organization,
        started_at__gte=start_date
    )

    stats = {
        'total_workflows': workflows.count(),
        'active_workflows': workflows.filter(status='active').count(),
        'draft_workflows': workflows.filter(status='draft').count(),
        'total_executions': executions.count(),
        'successful_executions': executions.filter(status='success').count(),
        'failed_executions': executions.filter(status='failed').count(),
        'success_rate': 0,
        'avg_execution_time': None,
        'most_used_workflows': [],
        'recent_workflows': []
    }

    # Calculate success rate
    if stats['total_executions'] > 0:
        stats['success_rate'] = round(
            (stats['successful_executions'] / stats['total_executions']) * 100, 2
        )

    # Calculate average execution time
    avg_time = executions.aggregate(avg=Avg('execution_time'))['avg']
    if avg_time:
        stats['avg_execution_time'] = avg_time.total_seconds()

    # Most used workflows
    most_used = workflows.annotate(
        execution_count=Count('executions')
    ).order_by('-execution_count')[:5]

    stats['most_used_workflows'] = [
        {
            'id': wf.id,
            'name': wf.name,
            'execution_count': wf.execution_count
        }
        for wf in most_used
    ]

    # Recent workflows
    recent = workflows.order_by('-created_at')[:5]
    stats['recent_workflows'] = [
        {
            'id': wf.id,
            'name': wf.name,
            'status': wf.status,
            'created_at': wf.created_at
        }
        for wf in recent
    ]

    return Response(stats)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_workflow(request, workflow_id):
    """
    Export workflow as JSON
    """
    try:
        organization = request.user.organization_memberships.first().organization
        workflow = Workflow.objects.get(
            id=workflow_id,
            organization=organization
        )

        # Create export data
        export_data = {
            'name': workflow.name,
            'description': workflow.description,
            'version': workflow.version,
            'category': workflow.category.name if workflow.category else None,
            'trigger_type': workflow.trigger_type,
            'nodes': workflow.nodes,
            'connections': workflow.connections,
            'variables': workflow.variables,
            'settings': workflow.settings,
            'tags': workflow.tags,
            'exported_at': timezone.now().isoformat(),
            'exported_by': request.user.username
        }

        # Return as downloadable file
        response = HttpResponse(
            json.dumps(export_data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="{workflow.name}.json"'

        return response

    except Workflow.DoesNotExist:
        return JsonResponse(
            {'error': 'Workflow not found'},
            status=404
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_workflow(request):
    """
    Import workflow from JSON
    """
    try:
        organization = request.user.organization_memberships.first().organization

        # Get import data
        if 'file' in request.FILES:
            # Import from file
            file_content = request.FILES['file'].read().decode('utf-8')
            import_data = json.loads(file_content)
        else:
            # Import from JSON data
            import_data = request.data

        # Validate required fields
        required_fields = ['name', 'nodes', 'connections']
        for field in required_fields:
            if field not in import_data:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Get or create category
        category = None
        if import_data.get('category'):
            category, _ = WorkflowCategory.objects.get_or_create(
                name=import_data['category']
            )

        # Create workflow
        workflow = Workflow.objects.create(
            organization=organization,
            name=import_data['name'],
            description=import_data.get('description', ''),
            category=category,
            trigger_type=import_data.get('trigger_type', 'manual'),
            nodes=import_data['nodes'],
            connections=import_data['connections'],
            variables=import_data.get('variables', {}),
            settings=import_data.get('settings', {}),
            tags=import_data.get('tags', []),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        serializer = WorkflowSerializer(workflow)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid JSON format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workflow_analytics(request, workflow_id):
    """
    Get detailed analytics for a specific workflow
    """
    try:
        organization = request.user.organization_memberships.first().organization
        workflow = Workflow.objects.get(
            id=workflow_id,
            organization=organization
        )

        # Get date range
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Get executions
        executions = WorkflowExecution.objects.filter(
            workflow=workflow,
            started_at__gte=start_date
        )

        # Calculate detailed metrics
        total_executions = executions.count()
        successful = executions.filter(status='success').count()
        failed = executions.filter(status='failed').count()
        cancelled = executions.filter(status='cancelled').count()

        # Performance metrics
        execution_times = [
            ex.execution_time.total_seconds()
            for ex in executions
            if ex.execution_time
        ]

        performance = {}
        if execution_times:
            performance = {
                'avg_execution_time': sum(execution_times) / len(execution_times),
                'min_execution_time': min(execution_times),
                'max_execution_time': max(execution_times),
                'median_execution_time': sorted(execution_times)[len(execution_times)//2]
            }

        # Hourly distribution
        hourly_distribution = {}
        for execution in executions:
            hour = execution.started_at.hour
            hourly_distribution[hour] = hourly_distribution.get(hour, 0) + 1

        # Error analysis
        error_types = {}
        failed_executions = executions.filter(status='failed')
        for execution in failed_executions:
            error_type = execution.error_message.split(':')[0] if execution.error_message else 'Unknown'
            error_types[error_type] = error_types.get(error_type, 0) + 1

        analytics = {
            'workflow': {
                'id': workflow.id,
                'name': workflow.name,
                'status': workflow.status,
                'version': workflow.version
            },
            'period': {
                'days': days,
                'start_date': start_date.isoformat(),
                'end_date': timezone.now().isoformat()
            },
            'summary': {
                'total_executions': total_executions,
                'successful_executions': successful,
                'failed_executions': failed,
                'cancelled_executions': cancelled,
                'success_rate': (successful / total_executions * 100) if total_executions > 0 else 0
            },
            'performance': performance,
            'patterns': {
                'hourly_distribution': hourly_distribution,
                'most_active_hours': sorted(hourly_distribution.items(), key=lambda x: x[1], reverse=True)[:3]
            },
            'errors': {
                'error_types': error_types,
                'most_common_errors': sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
            }
        }

        return Response(analytics)

    except Workflow.DoesNotExist:
        return Response(
            {'error': 'Workflow not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def clone_workflow(request, workflow_id):
    """
    Clone workflow with optional modifications
    """
    try:
        organization = request.user.organization_memberships.first().organization
        original_workflow = Workflow.objects.get(
            id=workflow_id,
            organization=organization
        )

        # Get clone parameters
        new_name = request.data.get('name', f"{original_workflow.name} (Clone)")
        new_description = request.data.get('description', f"Clone of {original_workflow.name}")
        modifications = request.data.get('modifications', {})

        # Create clone
        cloned_workflow = Workflow.objects.create(
            organization=organization,
            name=new_name,
            description=new_description,
            category=original_workflow.category,
            trigger_type=original_workflow.trigger_type,
            nodes=original_workflow.nodes.copy(),
            connections=original_workflow.connections.copy(),
            variables=original_workflow.variables.copy(),
            settings=original_workflow.settings.copy(),
            tags=original_workflow.tags.copy(),
            created_by=request.user,
            updated_by=request.user,
            status='draft'
        )

        # Apply modifications if provided
        if modifications:
            for field, value in modifications.items():
                if hasattr(cloned_workflow, field):
                    setattr(cloned_workflow, field, value)
            cloned_workflow.save()

        serializer = WorkflowSerializer(cloned_workflow)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Workflow.DoesNotExist:
        return Response(
            {'error': 'Workflow not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Clone failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )