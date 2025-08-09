"""
ASGI config for workflow_platform project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import apps.core.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'workflow_platform.settings.production')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    # Uncomment for WebSocket support
    # "websocket": AuthMiddlewareStack(
    #     URLRouter(
    #         apps.core.routing.websocket_urlpatterns
    #     )
    # ),
})