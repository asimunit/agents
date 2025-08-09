"""
Authentication URL Configuration
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    UserRegistrationView,
    UserProfileView,
    PasswordChangeView,
    PasswordResetView,
    LogoutView,
    OrganizationInviteView,
    AcceptInvitationView,
    user_organizations,
    switch_organization,
    auth_status
)

urlpatterns = [
    # Authentication endpoints
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', UserRegistrationView.as_view(), name='register'),

    # User profile
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('change-password/', PasswordChangeView.as_view(), name='change_password'),
    path('reset-password/', PasswordResetView.as_view(), name='reset_password'),

    # Organization management
    path('invite/', OrganizationInviteView.as_view(), name='organization_invite'),
    path('invite/<str:token>/', AcceptInvitationView.as_view(), name='accept_invitation'),
    path('organizations/', user_organizations, name='user_organizations'),
    path('switch-organization/', switch_organization, name='switch_organization'),

    # Status
    path('status/', auth_status, name='auth_status'),
]

app_name = 'authentication'