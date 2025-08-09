"""
Organizations Views - Organization management and administration
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta
import uuid

from .models import (
    Organization, OrganizationMember, OrganizationInvitation,
    OrganizationAPIKey, OrganizationUsage
)
from .serializers import (
    OrganizationSerializer, OrganizationMemberSerializer,
    OrganizationInvitationSerializer, OrganizationAPIKeySerializer,
    OrganizationUsageSerializer, OrganizationStatsSerializer,
    OrganizationSettingsSerializer, OrganizationInviteSerializer
)
from apps.core.permissions import OrganizationPermission, RoleBasedPermission
from apps.core.pagination import CustomPageNumberPagination


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Organization management
    """
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['plan', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get organizations for current user"""
        return Organization.objects.filter(
            members__user=self.request.user,
            members__status='active'
        ).distinct()

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get organization statistics"""
        organization = self.get_object()

        # Calculate statistics
        stats = self._calculate_organization_stats(organization)

        serializer = OrganizationStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'put'])
    def settings(self, request, pk=None):
        """Get or update organization settings"""
        organization = self.get_object()

        # Check permissions
        member = request.user.organization_memberships.filter(
            organization=organization
        ).first()

        if not member or member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.method == 'GET':
            serializer = OrganizationSettingsSerializer(organization)
            return Response(serializer.data)

        elif request.method == 'PUT':
            serializer = OrganizationSettingsSerializer(
                organization, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def invite_user(self, request, pk=None):
        """Invite user to organization"""
        organization = self.get_object()

        # Check permissions
        member = request.user.organization_memberships.filter(
            organization=organization
        ).first()

        if not member or member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = OrganizationInviteSerializer(
            data=request.data,
            context={'organization': organization, 'request': request}
        )

        if serializer.is_valid():
            # Create invitation
            invitation = OrganizationInvitation.objects.create(
                organization=organization,
                email=serializer.validated_data['email'],
                role=serializer.validated_data['role'],
                invited_by=request.user,
                token=uuid.uuid4().hex,
                expires_at=timezone.now() + timedelta(days=7)
            )

            # TODO: Send invitation email

            return Response({
                'message': 'Invitation sent successfully',
                'invitation_id': invitation.id,
                'expires_at': invitation.expires_at
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        """Get organization usage statistics"""
        organization = self.get_object()

        # Get date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        usage_data = OrganizationUsage.objects.filter(
            organization=organization,
            date__gte=start_date.date()
        ).order_by('date')

        # Calculate current usage
        current_usage = self._calculate_current_usage(organization)

        serializer = OrganizationUsageSerializer(usage_data, many=True)

        return Response({
            'current_usage': current_usage,
            'historical_usage': serializer.data,
            'period_days': days
        })

    def _calculate_organization_stats(self, organization):
        """Calculate organization statistics"""
        # User statistics
        users = OrganizationMember.objects.filter(
            organization=organization,
            status='active'
        ).count()

        # Workflow statistics
        from apps.workflows.models import Workflow
        workflows = Workflow.objects.filter(
            organization=organization,
            is_latest_version=True
        )

        active_workflows = workflows.filter(status='active').count()

        # Execution statistics
        from apps.executions.models import ExecutionHistory
        executions = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=timezone.now() - timedelta(days=30)
        )

        total_executions = executions.count()
        successful_executions = executions.filter(status='success').count()

        # Recent activity
        recent_activity = {
            'new_workflows_this_week': workflows.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
            'executions_this_week': executions.filter(
                started_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
            'new_members_this_month': OrganizationMember.objects.filter(
                organization=organization,
                joined_at__gte=timezone.now() - timedelta(days=30)
            ).count()
        }

        # Plan usage
        plan_usage = {
            'workflows_used': workflows.count(),
            'workflows_limit': organization.max_workflows,
            'users_count': users,
            'users_limit': organization.max_users,
            'executions_this_month': total_executions,
            'executions_limit': organization.max_executions_per_month
        }

        return {
            'users': users,
            'workflows': workflows.count(),
            'active_workflows': active_workflows,
            'total_executions': total_executions,
            'recent_activity': recent_activity,
            'plan_usage': plan_usage
        }

    def _calculate_current_usage(self, organization):
        """Calculate current usage metrics"""
        from apps.workflows.models import Workflow
        from apps.executions.models import ExecutionHistory

        # Current month executions
        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        current_month_executions = ExecutionHistory.objects.filter(
            organization=organization,
            started_at__gte=start_of_month
        ).count()

        return {
            'workflows': Workflow.objects.filter(
                organization=organization,
                is_latest_version=True
            ).count(),
            'users': OrganizationMember.objects.filter(
                organization=organization,
                status='active'
            ).count(),
            'executions_this_month': current_month_executions,
            'api_calls_this_hour': 0,  # TODO: Implement API call tracking
            'storage_used_mb': 0,  # TODO: Implement storage tracking
        }


class OrganizationMemberViewSet(viewsets.ModelViewSet):
    """
    Organization member management
    """
    serializer_class = OrganizationMemberSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['role', 'status']
    ordering = ['-joined_at']

    def get_queryset(self):
        """Get members for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationMember.objects.filter(
            organization=organization
        ).select_related('user', 'invited_by')

    @action(detail=True, methods=['post'])
    def change_role(self, request, pk=None):
        """Change member role"""
        member = self.get_object()

        # Check permissions
        requesting_member = request.user.organization_memberships.filter(
            organization=member.organization
        ).first()

        if not requesting_member or requesting_member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Prevent changing owner role unless requestor is owner
        if member.role == 'owner' and requesting_member.role != 'owner':
            return Response(
                {'error': 'Only owners can change owner roles'},
                status=status.HTTP_403_FORBIDDEN
            )

        new_role = request.data.get('role')
        if new_role not in ['member', 'admin', 'owner']:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        member.role = new_role
        member.save()

        return Response({
            'message': 'Role updated successfully',
            'new_role': new_role
        })

    @action(detail=True, methods=['post'])
    def remove(self, request, pk=None):
        """Remove member from organization"""
        member = self.get_object()

        # Check permissions
        requesting_member = request.user.organization_memberships.filter(
            organization=member.organization
        ).first()

        if not requesting_member or requesting_member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Prevent removing owners unless requestor is owner
        if member.role == 'owner' and requesting_member.role != 'owner':
            return Response(
                {'error': 'Only owners can remove other owners'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Prevent removing the last owner
        if member.role == 'owner':
            owner_count = OrganizationMember.objects.filter(
                organization=member.organization,
                role='owner',
                status='active'
            ).count()

            if owner_count <= 1:
                return Response(
                    {'error': 'Cannot remove the last owner'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        member.status = 'inactive'
        member.save()

        return Response({'message': 'Member removed successfully'})


class OrganizationAPIKeyViewSet(viewsets.ModelViewSet):
    """
    Organization API key management
    """
    serializer_class = OrganizationAPIKeySerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get API keys for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationAPIKey.objects.filter(
            organization=organization
        )

    def perform_create(self, serializer):
        """Create API key with organization context"""
        organization = self.request.user.organization_memberships.first().organization

        # Check permissions
        member = self.request.user.organization_memberships.filter(
            organization=organization
        ).first()

        if not member or member.role not in ['owner', 'admin']:
            raise PermissionError('Only owners and admins can create API keys')

        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """Regenerate API key"""
        api_key = self.get_object()

        # Check permissions
        member = request.user.organization_memberships.filter(
            organization=api_key.organization
        ).first()

        if not member or member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate new key
        api_key.generate_key()
        api_key.save()

        return Response({
            'message': 'API key regenerated successfully',
            'new_key': api_key.key
        })

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Revoke API key"""
        api_key = self.get_object()

        # Check permissions
        member = request.user.organization_memberships.filter(
            organization=api_key.organization
        ).first()

        if not member or member.role not in ['owner', 'admin']:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        api_key.is_active = False
        api_key.save()

        return Response({'message': 'API key revoked successfully'})


class OrganizationUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Organization usage analytics (read-only)
    """
    serializer_class = OrganizationUsageSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date']
    ordering = ['-date']

    def get_queryset(self):
        """Get usage data for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return OrganizationUsage.objects.filter(organization=organization)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_invitation(request, token):
    """
    Accept organization invitation
    """
    try:
        invitation = OrganizationInvitation.objects.get(
            token=token,
            status='pending'
        )

        # Check if invitation is expired
        if invitation.is_expired:
            invitation.status = 'expired'
            invitation.save()
            return Response(
                {'error': 'Invitation has expired'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user email matches invitation
        if request.user.email.lower() != invitation.email.lower():
            return Response(
                {'error': 'Email address does not match invitation'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user is already a member
        existing_member = OrganizationMember.objects.filter(
            organization=invitation.organization,
            user=request.user
        ).first()

        if existing_member:
            if existing_member.status == 'active':
                return Response(
                    {'error': 'You are already a member of this organization'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Reactivate existing member
                existing_member.status = 'active'
                existing_member.role = invitation.role
                existing_member.joined_at = timezone.now()
                existing_member.save()
        else:
            # Create new member
            OrganizationMember.objects.create(
                organization=invitation.organization,
                user=request.user,
                role=invitation.role,
                status='active',
                joined_at=timezone.now()
            )

        # Mark invitation as accepted
        invitation.status = 'accepted'
        invitation.accepted_at = timezone.now()
        invitation.save()

        return Response({
            'message': 'Invitation accepted successfully',
            'organization': {
                'id': invitation.organization.id,
                'name': invitation.organization.name,
                'slug': invitation.organization.slug
            },
            'role': invitation.role
        })

    except OrganizationInvitation.DoesNotExist:
        return Response(
            {'error': 'Invalid invitation token'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_organizations(request):
    """
    Get organizations for current user
    """
    memberships = OrganizationMember.objects.filter(
        user=request.user,
        status='active'
    ).select_related('organization')

    organizations = []
    for membership in memberships:
        organizations.append({
            'id': membership.organization.id,
            'name': membership.organization.name,
            'slug': membership.organization.slug,
            'plan': membership.organization.plan,
            'role': membership.role,
            'joined_at': membership.joined_at
        })

    return Response(organizations)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_organization(request):
    """
    Switch user's active organization context
    """
    organization_id = request.data.get('organization_id')

    if not organization_id:
        return Response(
            {'error': 'Organization ID is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        membership = OrganizationMember.objects.get(
            user=request.user,
            organization_id=organization_id,
            status='active'
        )

        # Set organization context (this would typically be stored in session/cache)
        request.session['active_organization_id'] = str(organization_id)

        return Response({
            'message': 'Organization switched successfully',
            'organization': {
                'id': membership.organization.id,
                'name': membership.organization.name,
                'slug': membership.organization.slug,
                'role': membership.role
            }
        })

    except OrganizationMember.DoesNotExist:
        return Response(
            {'error': 'Organization not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )