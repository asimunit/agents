"""
Core URL Configuration
"""
from django.urls import path
from .views import (
    health_check,
    system_status,
    custom_400_view,
    custom_403_view,
    custom_404_view,
    custom_500_view
)

urlpatterns = [
    # Health and status endpoints
    path('', health_check, name='health_check'),
    path('status/', system_status, name='system_status'),
]

# Error handler views
handler400 = custom_400_view
handler403 = custom_403_view
handler404 = custom_404_view
handler500 = custom_500_view

app_name = 'core'