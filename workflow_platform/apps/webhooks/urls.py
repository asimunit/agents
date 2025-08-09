"""
Webhooks URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WebhookEndpointViewSet,
    WebhookDeliveryViewSet,
    WebhookEventViewSet,
    WebhookTemplateViewSet,
    webhook_receiver,
    webhook_test,
    webhook_stats,
    WebhookViewSet
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'endpoints', WebhookEndpointViewSet, basename='webhook-endpoints')
router.register(r'deliveries', WebhookDeliveryViewSet, basename='webhook-deliveries')
router.register(r'events', WebhookEventViewSet, basename='webhook-events')
router.register(r'templates', WebhookTemplateViewSet, basename='webhook-templates')
router.register(r'', WebhookViewSet, basename='webhooks')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Webhook receiver endpoint
    path('receive/<str:url_path>/', webhook_receiver, name='webhook_receiver'),

    # Webhook testing
    path('test/<uuid:webhook_id>/', webhook_test, name='webhook_test'),

    # Statistics
    path('stats/', webhook_stats, name='webhook_stats'),
]

app_name = 'webhooks'