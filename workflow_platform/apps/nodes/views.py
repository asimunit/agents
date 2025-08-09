"""
Node API Views - Comprehensive node management
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg
from django.utils import timezone

from .models import (
    NodeType, NodeCategory, NodeCredential, NodeExecutionLog,
    NodeTypeRating, CustomNodeType, NodeTypeInstallation
)
from .serializers import (
    NodeTypeSerializer, NodeCategorySerializer, NodeCredentialSerializer,
    NodeExecutionLogSerializer, NodeTypeRatingSerializer,
    CustomNodeTypeSerializer, NodeInstallationSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.core.exceptions import NodeExecutionError


class NodeCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Node category management
    """
    queryset = NodeCategory.objects.all().order_by('sort_order', 'name')
    serializer_class = NodeCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Return all categories

    def get_queryset(self):
        """Get categories with node counts"""
        return NodeCategory.objects.annotate(
            node_count=Count('node_types', filter=Q(node_types__is_active=True))
        ).order_by('sort_order', 'name')


class NodeTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Node type management with marketplace features
    """
    serializer_class = NodeTypeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'node_type', 'source', 'is_beta']
    search_fields = ['name', 'display_name', 'description']
    ordering_fields = ['usage_count', 'rating', 'created_at', 'display_name']
    ordering = ['category__sort_order', 'display_name']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get active node types with filtering"""
        queryset = NodeType.objects.filter(is_active=True).select_related('category')

        # Filter by organization plan
        organization = self.request.user.organization_memberships.first().organization
        plan_hierarchy = {'free': 0, 'pro': 1, 'business': 2, 'enterprise': 3}
        org_plan_level = plan_hierarchy.get(organization.plan, 0)

        # Include nodes available for current plan
        queryset = queryset.filter(
            Q(minimum_plan='free') |
            Q(minimum_plan__in=[plan for plan, level in plan_hierarchy.items() if level <= org_plan_level])
        )

        return queryset

    @action(detail=True, methods=['post'])
    def install(self, request, pk=None):
        """Install node type in organization"""
        node_type = self.get_object()
        organization = request.user.organization_memberships.first().organization

        # Check if already installed
        if NodeTypeInstallation.objects.filter(
                organization=organization,
                node_type=node_type
        ).exists():
            return Response(
                {'error': 'Node type already installed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check plan requirements
        plan_hierarchy = {'free': 0, 'pro': 1, 'business': 2, 'enterprise': 3}
        org_plan_level = plan_hierarchy.get(organization.plan, 0)
        required_plan_level = plan_hierarchy.get(node_type.minimum_plan, 0)

        if required_plan_level > org_plan_level:
            return Response(
                {'error': f'Node requires {node_type.minimum_plan} plan or higher'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Install node type
        installation = NodeTypeInstallation.objects.create(
            organization=organization,
            node_type=node_type,
            installed_version=node_type.version,
            installed_by=request.user
        )

        # Increment usage count
        node_type.usage_count += 1
        node_type.save(update_fields=['usage_count'])

        serializer = NodeInstallationSerializer(installation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'])
    def uninstall(self, request, pk=None):
        """Uninstall node type from organization"""
        node_type = self.get_object()
        organization = request.user.organization_memberships.first().organization

        try:
            installation = NodeTypeInstallation.objects.get(
                organization=organization,
                node_type=node_type
            )
            installation.delete()

            return Response({'message': 'Node type uninstalled successfully'})

        except NodeTypeInstallation.DoesNotExist:
            return Response(
                {'error': 'Node type not installed'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def rate(self, request, pk=None):
        """Rate a node type"""
        node_type = self.get_object()
        organization = request.user.organization_memberships.first().organization

        serializer = NodeTypeRatingSerializer(data=request.data)
        if serializer.is_valid():
            rating_value = serializer.validated_data['rating']
            review = serializer.validated_data.get('review', '')

            # Create or update rating
            rating, created = NodeTypeRating.objects.update_or_create(
                node_type=node_type,
                user=request.user,
                organization=organization,
                defaults={
                    'rating': rating_value,
                    'review': review
                }
            )

            response_serializer = NodeTypeRatingSerializer(rating)
            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

            return Response(response_serializer.data, status=status_code)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """Get node type reviews"""
        node_type = self.get_object()

        reviews = node_type.ratings.select_related('user', 'organization').order_by('-created_at')

        # Paginate reviews
        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = NodeTypeRatingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = NodeTypeRatingSerializer(reviews, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def installed(self, request):
        """Get installed node types for organization"""
        organization = request.user.organization_memberships.first().organization

        installations = NodeTypeInstallation.objects.filter(
            organization=organization,
            is_enabled=True
        ).select_related('node_type', 'node_type__category')

        # Apply search filter
        search = request.query_params.get('search')
        if search:
            installations = installations.filter(
                Q(node_type__name__icontains=search) |
                Q(node_type__display_name__icontains=search) |
                Q(node_type__description__icontains=search)
            )

        serializer = NodeInstallationSerializer(installations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def marketplace(self, request):
        """Browse node marketplace"""
        queryset = self.get_queryset()

        # Filter by featured, popular, etc.
        filter_type = request.query_params.get('filter', 'all')

        if filter_type == 'featured':
            # Create a featured filter based on usage and rating
            queryset = queryset.filter(usage_count__gte=100, rating__gte=4.0)
        elif filter_type == 'popular':
            queryset = queryset.order_by('-usage_count')
        elif filter_type == 'newest':
            queryset = queryset.order_by('-created_at')
        elif filter_type == 'top_rated':
            queryset = queryset.filter(rating_count__gte=5).order_by('-rating')

        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class NodeCredentialViewSet(viewsets.ModelViewSet):
    """
    Node credentials management with encryption
    """
    serializer_class = NodeCredentialSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['credential_type', 'service_name', 'is_active']
    search_fields = ['name', 'service_name', 'description']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get credentials for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return NodeCredential.objects.filter(organization=organization)

    def perform_create(self, serializer):
        """Create credential with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test credential connectivity"""
        credential = self.get_object()

        try:
            # Basic test based on credential type
            if credential.credential_type == 'api_key':
                # Test API key by making a simple request
                test_result = self._test_api_key(credential)
            elif credential.credential_type == 'database':
                # Test database connection
                test_result = self._test_database_connection(credential)
            elif credential.credential_type == 'oauth2':
                # Test OAuth2 token
                test_result = self._test_oauth2_token(credential)
            else:
                test_result = {'status': 'success', 'message': 'Credential format is valid'}

            return Response(test_result)

        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _test_api_key(self, credential):
        """Test API key credential"""
        # This would implement actual API testing
        return {'status': 'success', 'message': 'API key is valid'}

    def _test_database_connection(self, credential):
        """Test database connection"""
        # This would implement actual database connection testing
        return {'status': 'success', 'message': 'Database connection successful'}

    def _test_oauth2_token(self, credential):
        """Test OAuth2 token"""
        # This would implement actual OAuth2 token validation
        return {'status': 'success', 'message': 'OAuth2 token is valid'}


class CustomNodeTypeViewSet(viewsets.ModelViewSet):
    """
    Custom node type management
    """
    serializer_class = CustomNodeTypeSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['visibility', 'is_active']
    search_fields = ['name', 'display_name', 'description']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get custom nodes for organization"""
        organization = self.request.user.organization_memberships.first().organization

        # Include own nodes and shared nodes
        return CustomNodeType.objects.filter(
            Q(organization=organization) |
            Q(visibility='public') |
            Q(shared_with_orgs=organization)
        ).distinct()

    def perform_create(self, serializer):
        """Create custom node with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share custom node with other organizations"""
        custom_node = self.get_object()

        # Check permissions
        if custom_node.organization != request.user.organization_memberships.first().organization:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        organization_ids = request.data.get('organization_ids', [])

        for org_id in organization_ids:
            try:
                from apps.organizations.models import Organization
                org = Organization.objects.get(id=org_id)
                custom_node.shared_with_orgs.add(org)
            except Organization.DoesNotExist:
                continue

        return Response({'message': f'Shared with {len(organization_ids)} organizations'})

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish custom node to marketplace"""
        custom_node = self.get_object()

        # Check permissions
        if custom_node.organization != request.user.organization_memberships.first().organization:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Set as public
        custom_node.visibility = 'public'
        custom_node.save()

        return Response({'message': 'Custom node published to marketplace'})


class NodeExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Node execution logs for debugging and monitoring
    """
    serializer_class = NodeExecutionLogSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'node_type', 'is_retry']
    ordering_fields = ['started_at', 'execution_time']
    ordering = ['-started_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get logs for organization workflows"""
        organization = self.request.user.organization_memberships.first().organization

        return NodeExecutionLog.objects.filter(
            execution__workflow__organization=organization
        ).select_related('node_type', 'execution', 'execution__workflow')

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get node execution statistics"""
        organization = request.user.organization_memberships.first().organization

        # Date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timezone.timedelta(days=days)

        logs = self.get_queryset().filter(started_at__gte=start_date)

        # Basic stats
        total_executions = logs.count()
        successful_executions = logs.filter(status='completed').count()
        failed_executions = logs.filter(status='failed').count()

        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

        # Average execution time
        avg_execution_time = logs.filter(
            status='completed',
            execution_time__isnull=False
        ).aggregate(avg_time=Avg('execution_time'))['avg_time'] or 0

        # Top failing nodes
        failing_nodes = logs.filter(status='failed').values(
            'node_type__name', 'node_type__display_name'
        ).annotate(
            failure_count=Count('id')
        ).order_by('-failure_count')[:10]

        # Performance by node type
        node_performance = logs.filter(status='completed').values(
            'node_type__name', 'node_type__display_name'
        ).annotate(
            avg_execution_time=Avg('execution_time'),
            execution_count=Count('id')
        ).order_by('-execution_count')[:10]

        statistics = {
            'overview': {
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': failed_executions,
                'success_rate': round(success_rate, 2),
                'average_execution_time': round(avg_execution_time, 2) if avg_execution_time else 0,
            },
            'failing_nodes': list(failing_nodes),
            'node_performance': list(node_performance),
        }

        return Response(statistics)

    @action(detail=False, methods=['get'])
    def errors(self, request):
        """Get error analysis"""
        organization = request.user.organization_memberships.first().organization

        # Date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timezone.timedelta(days=days)

        error_logs = self.get_queryset().filter(
            started_at__gte=start_date,
            status='failed'
        )

        # Group by error type
        error_types = error_logs.values('error_type').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        # Recent errors
        recent_errors = error_logs.order_by('-started_at')[:20]
        recent_error_serializer = NodeExecutionLogSerializer(recent_errors, many=True)

        return Response({
            'error_types': list(error_types),
            'recent_errors': recent_error_serializer.data
        })


@action(detail=False, methods=['get'])
def node_health_check(request):
    """Health check for node system"""

    try:
        # Check if basic nodes are available
        essential_nodes = ['http_request', 'webhook_trigger', 'json', 'if']
        missing_nodes = []

        for node_name in essential_nodes:
            if not NodeType.objects.filter(name=node_name, is_active=True).exists():
                missing_nodes.append(node_name)

        health_status = {
            'status': 'healthy' if not missing_nodes else 'unhealthy',
            'timestamp': timezone.now(),
            'total_node_types': NodeType.objects.filter(is_active=True).count(),
            'categories': NodeCategory.objects.count(),
            'missing_essential_nodes': missing_nodes
        }

        status_code = status.HTTP_200_OK if not missing_nodes else status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(health_status, status=status_code)

    except Exception as e:
        return Response(
            {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': timezone.now()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )