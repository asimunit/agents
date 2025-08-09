"""
Main URL Configuration for Workflow Platform
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API Routes
    path('api/v1/auth/', include('apps.authentication.urls')),
    path('api/v1/organizations/', include('apps.organizations.urls')),
    path('api/v1/workflows/', include('apps.workflows.urls')),
    path('api/v1/nodes/', include('apps.nodes.urls')),
    path('api/v1/executions/', include('apps.executions.urls')),
    path('api/v1/webhooks/', include('apps.webhooks.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),

    # Health Check
    path('health/', include('apps.core.urls')),

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path('schema/', SpectacularAPIView.as_view(), name='schema-alt'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui-alt'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc-alt'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom error handlers
handler400 = 'apps.core.views.custom_400_view'
handler403 = 'apps.core.views.custom_403_view'
handler404 = 'apps.core.views.custom_404_view'
handler500 = 'apps.core.views.custom_500_view'