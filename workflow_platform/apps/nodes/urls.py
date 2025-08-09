"""
Nodes URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NodeCategoryViewSet,
    NodeTypeViewSet,
    NodeCredentialViewSet,
    CustomNodeTypeViewSet,
    NodeExecutionLogViewSet,
    node_health_check
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'categories', NodeCategoryViewSet, basename='node-categories')
router.register(r'types', NodeTypeViewSet, basename='node-types')
router.register(r'credentials', NodeCredentialViewSet, basename='node-credentials')
router.register(r'custom', CustomNodeTypeViewSet, basename='custom-node-types')
router.register(r'logs', NodeExecutionLogViewSet, basename='node-execution-logs')

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),

    # Health check
    path('health/', node_health_check, name='node_health_check'),
]

app_name = 'nodes'