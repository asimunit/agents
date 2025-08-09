"""
Organizations URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet,
    OrganizationMemberViewSet,
    OrganizationUsageViewSet,
    OrganizationAPIKeyViewSet
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'', OrganizationViewSet, basename='organizations')
router.register(r'members', OrganizationMemberViewSet, basename='organization-members')
router.register(r'usage', OrganizationUsageViewSet, basename='organization-usage')
router.register(r'api-keys', OrganizationAPIKeyViewSet, basename='organization-api-keys')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]

app_name = 'organizations'