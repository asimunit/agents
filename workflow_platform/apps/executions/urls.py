"""
Executions URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExecutionQueueViewSet,
    ExecutionHistoryViewSet,
    ExecutionAlertViewSet,
    ExecutionResourceViewSet,
    ExecutionScheduleViewSet,
    trigger_workflow,
    execution_status,
    execution_stats
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'queue', ExecutionQueueViewSet, basename='execution-queue')
router.register(r'history', ExecutionHistoryViewSet, basename='execution-history')
router.register(r'alerts', ExecutionAlertViewSet, basename='execution-alerts')
router.register(r'resources', ExecutionResourceViewSet, basename='execution-resources')
router.register(r'schedules', ExecutionScheduleViewSet, basename='execution-schedules')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Custom endpoints
    path('trigger/<uuid:workflow_id>/', trigger_workflow, name='trigger_workflow'),
    path('status/<str:execution_id>/', execution_status, name='execution_status'),
    path('stats/', execution_stats, name='execution_stats'),
]

app_name = 'executions'