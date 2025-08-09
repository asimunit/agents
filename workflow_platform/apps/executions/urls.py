"""
Executions URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkflowExecutionViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'', WorkflowExecutionViewSet, basename='executions')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]

app_name = 'executions'