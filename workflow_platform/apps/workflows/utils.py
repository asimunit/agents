"""
Workflow URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkflowViewSet,
    WorkflowExecutionViewSet,
    WorkflowTemplateViewSet
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'workflows', WorkflowViewSet, basename='workflows')
router.register(r'executions', WorkflowExecutionViewSet, basename='workflow-executions')
router.register(r'templates', WorkflowTemplateViewSet, basename='workflow-templates')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]

app_name = 'workflows'