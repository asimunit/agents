"""
Organization Views - Multi-tenant organization management
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta

from .models import (
    Organization, OrganizationMember, OrganizationUsage,
    OrganizationAPIKey, OrganizationInvitation
)
from .serializers import (
    OrganizationSerializer, OrganizationMemberSerializer,
    OrganizationUsageSerializer, OrganizationAPIKeySerializer,
    OrganizationInvitationSerializer
)
from apps.core.permissions import OrganizationPermission, AdminPermission, OwnerPermission
from apps.core.pagination import CustomPageNumberPagination


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Organization management viewset
    """
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    pagination_class = None  # Single organization per user context

    def get_queryset(self):
        """Get user's organization"""
        return Organization.objects.filter(
            members__user=self.request.user,
            members__status='active'
        )

    def get_object(self):
        """Get current user's organization"""
        try:
            membership = self.request.user.organization_memberships.filter(status='active').first()
            return membership.organization
        except AttributeError:
            from django.http import Http404
            raise Http404("Organization not found")

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current organization details"""
        try:
            organization = self.get_object()
            serializer = self.get_serializer(organization)
            return Response(serializer.data)
        except Exception:
            return Response(
                {'error': 'No active organization found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get organization statistics"""
        organization = self.get_object()

        # Basic statistics
        stats = {
            'users': organization.members.filter(status='active').count(),
            'workflows': organization.workflows.count(),
            'active_workflows': organization.workflows.filter(status='active').count(),
            'total_executions': organization.workflows.aggregate(
                total=Sum('total_executions')
            )['total'] or 0,
        }

        # Recent activity (last 30 days)
        start_date = timezone.now() - timedelta(days=30)
        recent_executions = organization.workflows.filter(
            executions__started_at__gte=start_date
        ).aggregate(
            count=Count('executions'),
            avg_time=Avg('executions__execution_time')
        )

        stats['recent_activity'] = {
            'executions_last_30_days': recent_executions['count'] or 0,
            'avg_execution_time': round(recent_executions['avg_time'] or 0, 2),
        }

        # Plan usage
        limits = organization.get_usage_limits()
        stats['plan_usage'] = {
            'plan': organization.plan,
            'workflows_used': stats['workflows'],
            'workflows_limit': limits['max_workflows'],
            'users_used': stats['users'],
            'users_limit': limits['max_users'],
        }

        return Response(stats)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, AdminPermission])
    def upgrade_plan(self, request, pk=None):
        """Upgrade organization plan"""
        organization = self.get_object()
        new_plan = request.data.get('plan')

        if new_plan not in dict(Organization.PLAN_CHOICES):
            return Response(
                {'error': 'Invalid plan'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update plan and limits
        organization.plan = new_plan
        limits = organization.get_usage_limits()
        organization.max_workflows = limits['max_workflows']
        organization.max_executions_per_month = limits['max_executions_per_month']
        organization.max_users = limits['max_users']
        organization.max_api_calls_per_hour = limits['max_api_calls_per_hour']
        organization.save()

        return Response({
            'message': f'Plan upgraded to {new_plan}',
            'new_limits': limits
        })


class OrganizationMemberViewSet(viewsets.ModelViewSet):
    """
    Organization member management
    """
    serializer_class = OrganizationMemberSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['role', 'status']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get members for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationMember.objects.filter(organization=organization).select_related('user')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, AdminPermission])
    def change_role(self, request, pk=None):
        """Change member role"""
        member = self.get_object()
        new_role = request.data.get('role')

        if new_role not in dict(OrganizationMember.ROLE_CHOICES):
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prevent demoting the last owner
        if member.role == 'owner' and new_role != 'owner':
            owner_count = OrganizationMember.objects.filter(
                organization=member.organization,
                role='owner',
                status='active'
            ).count()

            if owner_count <= 1:
                return Response(
                    {'error': 'Cannot demote the last owner'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        member.role = new_role
        member.save()

        return Response({
            'message': f'Role changed to {new_role}',
            'member': OrganizationMemberSerializer(member).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, AdminPermission])
    def deactivate(self, request, pk=None):
        """Deactivate member"""
        member = self.get_object()

        # Prevent deactivating the last owner
        if member.role == 'owner':
            owner_count = OrganizationMember.objects.filter(
                organization=member.organization,
                role='owner',
                status='active'
            ).count()

            if owner_count <= 1:
                return Response(
                    {'error': 'Cannot deactivate the last owner'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        member.status = 'inactive'
        member.save()

        return Response({'message': 'Member deactivated'})


class OrganizationUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Organization usage tracking
    """
    serializer_class = OrganizationUsageSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    ordering = ['-period_start']

    def get_queryset(self):
        """Get usage records for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationUsage.objects.filter(organization=organization)

    @action(detail=False, methods=['get'])
    def current_month(self, request):
        """Get current month usage"""
        organization = request.user.organization_memberships.first().organization

        # Get current month start
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            usage = OrganizationUsage.objects.get(
                organization=organization,
                period_start=month_start
            )
            serializer = self.get_serializer(usage)
            return Response(serializer.data)
        except OrganizationUsage.DoesNotExist:
            # Return empty usage if not found
            return Response({
                'workflow_executions': 0,
                'api_calls': 0,
                'storage_used_mb': 0,
                'bandwidth_used_mb': 0,
                'total_cost': 0,
                'period_start': month_start,
                'period_end': now,
            })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get usage summary"""
        organization = request.user.organization_memberships.first().organization

        # Get last 12 months
        end_date = timezone.now()
        start_date = end_date - timedelta(days=365)

        usage_records = self.get_queryset().filter(
            period_start__gte=start_date
        )

        total_usage = usage_records.aggregate(
            total_executions=Sum('workflow_executions'),
            total_api_calls=Sum('api_calls'),
            total_cost=Sum('total_cost'),
            avg_storage=Avg('storage_used_mb')
        )

        return Response({
            'period': '12 months',
            'total_executions': total_usage['total_executions'] or 0,
            'total_api_calls': total_usage['total_api_calls'] or 0,
            'total_cost': float(total_usage['total_cost'] or 0),
            'avg_storage_mb': round(total_usage['avg_storage'] or 0, 2),
            'records_count': usage_records.count(),
        })


class OrganizationAPIKeyViewSet(viewsets.ModelViewSet):
    """
    Organization API key management
    """
    serializer_class = OrganizationAPIKeySerializer
    permission_classes = [IsAuthenticated, AdminPermission]
    ordering = ['-created_at']

    def get_queryset(self):
        """Get API keys for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationAPIKey.objects.filter(organization=organization)

    def perform_create(self, serializer):
        """Create API key with organization context"""
        organization = self.request.user.organization_memberships.first().organization
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """Regenerate API key"""
        api_key = self.get_object()

        # Generate new key
        import secrets
        api_key.key = f"wp_{secrets.token_urlsafe(32)}"
        api_key.key_preview = api_key.key[:8] + "..."
        api_key.save()

        return Response({
            'message': 'API key regenerated',
            'new_key': api_key.key,  # Only return once
            'key_preview': api_key.key_preview
        })

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate API key"""
        api_key = self.get_object()
        api_key.is_active = False
        api_key.save()

        return Response({'message': 'API key deactivated'})