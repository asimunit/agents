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
import logging

logger = logging.getLogger(__name__)

# Targeted Fixes for Remaining 500 Errors

# 1. FIX: Organizations 500 Error
# File: apps/organizations/views.py
# REPLACE the entire OrganizationViewSet with this:

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from .models import Organization, OrganizationMember
from .serializers import OrganizationSerializer
import logging

logger = logging.getLogger(__name__)


class OrganizationViewSet(viewsets.ModelViewSet):
    """Organization management with proper error handling"""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get organizations for current user with proper error handling"""
        # Handle schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Organization.objects.none()

        try:
            # Check if user is authenticated
            if not self.request.user.is_authenticated:
                return Organization.objects.none()

            # Check if user has organization memberships
            if not hasattr(self.request.user, 'organization_memberships'):
                return Organization.objects.none()

            memberships = self.request.user.organization_memberships.filter(status='active')

            if memberships.exists():
                # Get organizations from memberships
                org_ids = memberships.values_list('organization_id', flat=True)
                return Organization.objects.filter(id__in=org_ids)
            else:
                # User has no organizations, return empty queryset
                return Organization.objects.none()

        except Exception as e:
            logger.error(f"Error in OrganizationViewSet.get_queryset: {e}")
            return Organization.objects.none()

    def perform_create(self, serializer):
        """Create organization with better error handling"""
        try:
            organization = serializer.save(created_by=self.request.user)

            # Create owner membership for the user
            OrganizationMember.objects.create(
                organization=organization,
                user=self.request.user,
                role='owner',
                status='active',
                joined_at=timezone.now()
            )

        except Exception as e:
            logger.error(f"Error creating organization: {e}")
            raise ValidationError(f"Failed to create organization: {str(e)}")

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """Get organization members"""
        try:
            organization = self.get_object()
            members = organization.members.filter(status='active').select_related('user')

            members_data = []
            for member in members:
                members_data.append({
                    'id': member.id,
                    'user': {
                        'id': member.user.id,
                        'username': member.user.username,
                        'email': member.user.email,
                        'first_name': member.user.first_name,
                        'last_name': member.user.last_name,
                    },
                    'role': member.role,
                    'joined_at': member.joined_at
                })

            return Response(members_data)
        except Exception as e:
            logger.error(f"Error getting organization members: {e}")
            return Response({'error': str(e)}, status=500)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get organization statistics"""
        try:
            organization = self.get_object()

            stats = {
                'total_members': organization.members.filter(status='active').count(),
                'total_workflows': organization.workflows.count(),
                'active_workflows': organization.workflows.filter(status='active').count(),
                'total_executions': 0,  # Would calculate from executions
                'plan': organization.plan,
                'created_at': organization.created_at
            }

            return Response(stats)
        except Exception as e:
            logger.error(f"Error getting organization stats: {e}")
            return Response({'error': str(e)}, status=500)


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


