"""
Analytics URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnalyticsDashboardViewSet,
    AnalyticsWidgetViewSet,
    AnalyticsReportViewSet,
    AnalyticsMetricViewSet,
    UsageAnalyticsViewSet,
    PerformanceMetricsViewSet,
    AnalyticsAlertViewSet,
    overview_stats,
    workflow_analytics
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'dashboards', AnalyticsDashboardViewSet, basename='analytics-dashboards')
router.register(r'widgets', AnalyticsWidgetViewSet, basename='analytics-widgets')
router.register(r'reports', AnalyticsReportViewSet, basename='analytics-reports')
router.register(r'metrics', AnalyticsMetricViewSet, basename='analytics-metrics')
router.register(r'usage', UsageAnalyticsViewSet, basename='usage-analytics')
router.register(r'performance', PerformanceMetricsViewSet, basename='performance-metrics')
router.register(r'alerts', AnalyticsAlertViewSet, basename='analytics-alerts')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Custom analytics endpoints
    path('overview/', overview_stats, name='overview_stats'),
    path('workflows/<uuid:workflow_id>/', workflow_analytics, name='workflow_analytics'),
]

app_name = 'analytics'