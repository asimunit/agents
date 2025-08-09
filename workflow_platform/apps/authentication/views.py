"""
Authentication Views - Advanced auth system with organization support
"""
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
import uuid

from .serializers import (
    CustomTokenObtainPairSerializer, UserRegistrationSerializer,
    UserProfileSerializer, PasswordChangeSerializer, PasswordResetSerializer,
    OrganizationInvitationSerializer
)
from apps.organizations.models import Organization, OrganizationMember, OrganizationInvitation
from apps.core.permissions import IsAuthenticated


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token view with organization context
    """
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # Add user and organization info to response
            user = authenticate(
                username=request.data.get('username'),
                password=request.data.get('password')
            )

            if user:
                # Get user's organization
                try:
                    membership = user.organization_memberships.filter(status='active').first()
                    if membership:
                        response.data.update({
                            'user': {
                                'id': user.id,
                                'username': user.username,
                                'email': user.email,
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                            },
                            'organization': {
                                'id': membership.organization.id,
                                'name': membership.organization.name,
                                'slug': membership.organization.slug,
                                'plan': membership.organization.plan,
                                'role': membership.role,
                            }
                        })
                except Exception:
                    pass

        return response


class UserRegistrationView(APIView):
    """
    User registration with automatic organization creation
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # Create user
                    user = serializer.save()

                    # Create organization if not joining existing one
                    invitation_token = request.data.get('invitation_token')

                    if invitation_token:
                        # Join existing organization via invitation
                        try:
                            invitation = OrganizationInvitation.objects.get(
                                token=invitation_token,
                                status='pending',
                                expires_at__gt=timezone.now()
                            )

                            # Create membership
                            OrganizationMember.objects.create(
                                organization=invitation.organization,
                                user=user,
                                role=invitation.role,
                                status='active',
                                joined_at=timezone.now()
                            )

                            # Mark invitation as accepted
                            invitation.status = 'accepted'
                            invitation.accepted_at = timezone.now()
                            invitation.save()

                            organization = invitation.organization

                        except OrganizationInvitation.DoesNotExist:
                            return Response(
                                {'error': 'Invalid or expired invitation'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    else:
                        # Create new organization
                        org_name = request.data.get('organization_name', f"{user.username}'s Organization")

                        organization = Organization.objects.create(
                            name=org_name,
                            slug=f"{user.username}-org-{uuid.uuid4().hex[:8]}",
                            created_by=user,
                            plan='free',  # Start with free plan
                            max_workflows=5,
                            max_executions_per_month=1000,
                            max_users=1,
                        )

                        # Create owner membership
                        OrganizationMember.objects.create(
                            organization=organization,
                            user=user,
                            role='owner',
                            status='active',
                            joined_at=timezone.now()
                        )

                    # Generate tokens
                    refresh = RefreshToken.for_user(user)

                    return Response({
                        'message': 'Registration successful',
                        'user': {
                            'id': user.id,
                            'username': user.username,
                            'email': user.email,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                        },
                        'organization': {
                            'id': organization.id,
                            'name': organization.name,
                            'slug': organization.slug,
                            'plan': organization.plan,
                        },
                        'tokens': {
                            'refresh': str(refresh),
                            'access': str(refresh.access_token),
                        }
                    }, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response(
                    {'error': f'Registration failed: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    """
    User profile management
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user profile"""
        serializer = UserProfileSerializer(request.user)

        # Add organization info
        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            data = serializer.data

            if membership:
                data['organization'] = {
                    'id': membership.organization.id,
                    'name': membership.organization.name,
                    'slug': membership.organization.slug,
                    'plan': membership.organization.plan,
                    'role': membership.role,
                }

            return Response(data)

        except Exception:
            return Response(serializer.data)

    def put(self, request):
        """Update user profile"""
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordChangeView(APIView):
    """
    Change user password
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'user': request.user})

        if serializer.is_valid():
            # Change password
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save()

            return Response({'message': 'Password changed successfully'})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetView(APIView):
    """
    Password reset request
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)

        if serializer.is_valid():
            # In production, send reset email
            # For now, return success regardless
            return Response({
                'message': 'Password reset instructions sent to your email'
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    Logout user by blacklisting refresh token
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({'message': 'Logout successful'})

        except Exception:
            return Response(
                {'error': 'Invalid token'},
                status=status.HTTP_400_BAD_REQUEST
            )


class OrganizationInviteView(APIView):
    """
    Send organization invitations
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Send invitation to join organization"""

        # Check if user has permission to invite
        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership or membership.role not in ['owner', 'admin']:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )

            organization = membership.organization

            # Check organization limits
            current_members = organization.members.filter(status='active').count()
            if current_members >= organization.max_users:
                return Response(
                    {'error': 'Organization member limit reached'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = OrganizationInvitationSerializer(data=request.data)

            if serializer.is_valid():
                email = serializer.validated_data['email']
                role = serializer.validated_data.get('role', 'member')

                # Check if user already exists
                if User.objects.filter(email=email).exists():
                    return Response(
                        {'error': 'User with this email already exists'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Check if invitation already exists
                if OrganizationInvitation.objects.filter(
                        organization=organization,
                        email=email,
                        status='pending'
                ).exists():
                    return Response(
                        {'error': 'Invitation already sent'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create invitation
                invitation = OrganizationInvitation.objects.create(
                    organization=organization,
                    email=email,
                    role=role,
                    invited_by=request.user,
                    token=uuid.uuid4().hex,
                    expires_at=timezone.now() + timezone.timedelta(days=7)
                )

                # In production, send invitation email here
                # send_invitation_email(invitation)

                return Response({
                    'message': 'Invitation sent successfully',
                    'invitation_id': invitation.id,
                    'invitation_url': f'/invite/{invitation.token}'
                }, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response(
                {'error': f'Failed to send invitation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AcceptInvitationView(APIView):
    """
    Accept organization invitation
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        """Get invitation details"""
        try:
            invitation = OrganizationInvitation.objects.get(
                token=token,
                status='pending',
                expires_at__gt=timezone.now()
            )

            return Response({
                'organization': {
                    'name': invitation.organization.name,
                    'plan': invitation.organization.plan,
                },
                'role': invitation.role,
                'invited_by': invitation.invited_by.get_full_name() or invitation.invited_by.username,
                'expires_at': invitation.expires_at,
            })

        except OrganizationInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired invitation'},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request, token):
        """Accept invitation (handled in registration)"""
        return Response({
            'message': 'Use this token during registration to join the organization'
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_organizations(request):
    """Get user's organizations"""

    memberships = request.user.organization_memberships.filter(
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
            'joined_at': membership.joined_at,
        })

    return Response(organizations)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_organization(request):
    """Switch active organization"""

    organization_id = request.data.get('organization_id')

    try:
        membership = request.user.organization_memberships.get(
            organization_id=organization_id,
            status='active'
        )

        # In a more complex setup, you might update session/cache here
        # For now, just return the organization details

        return Response({
            'organization': {
                'id': membership.organization.id,
                'name': membership.organization.name,
                'slug': membership.organization.slug,
                'plan': membership.organization.plan,
                'role': membership.role,
            }
        })

    except OrganizationMember.DoesNotExist:
        return Response(
            {'error': 'Organization not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def auth_status(request):
    """Check authentication status"""

    if request.user.is_authenticated:
        try:
            membership = request.user.organization_memberships.filter(status='active').first()

            return Response({
                'authenticated': True,
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'email': request.user.email,
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                },
                'organization': {
                    'id': membership.organization.id,
                    'name': membership.organization.name,
                    'slug': membership.organization.slug,
                    'plan': membership.organization.plan,
                    'role': membership.role,
                } if membership else None
            })

        except Exception:
            return Response({
                'authenticated': True,
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'email': request.user.email,
                },
                'organization': None
            })

    return Response({'authenticated': False})