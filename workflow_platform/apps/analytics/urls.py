"""
Analytics URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnalyticsDashboardViewSet,
    MetricDefinitionViewSet,
    ErrorAnalyticsViewSet,
    AlertRuleViewSet,
    overview_analytics,
    performance_analytics,
    usage_analytics,
    business_analytics,
    real_time_metrics
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'dashboards', AnalyticsDashboardViewSet, basename='analytics-dashboards')
router.register(r'metrics', MetricDefinitionViewSet, basename='metric-definitions')
router.register(r'errors', ErrorAnalyticsViewSet, basename='error-analytics')
router.register(r'alerts', AlertRuleViewSet, basename='alert-rules')

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),

    # Analytics views
    path('overview/', overview_analytics, name='overview_analytics'),
    path('performance/', performance_analytics, name='performance_analytics'),
    path('usage/', usage_analytics, name='usage_analytics'),
    path('business/', business_analytics, name='business_analytics'),
    path('real-time/', real_time_metrics, name='real_time_metrics'),
]

app_name = 'analytics'