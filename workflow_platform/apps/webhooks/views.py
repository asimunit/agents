"""
Webhook Views - Advanced webhook handling and management
"""
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.conf import settings
import json
import uuid
import hashlib
import hmac
import logging
import requests
from datetime import timedelta

from .models import (
    WebhookEndpoint, WebhookDelivery, WebhookRateLimit,
    WebhookEvent, WebhookTemplate
)
from .serializers import (
    WebhookEndpointSerializer, WebhookDeliverySerializer,
    WebhookEventSerializer, WebhookTemplateSerializer,
    WebhookEndpointCreateSerializer, WebhookStatsSerializer,
    WebhookTestSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.workflows.models import Workflow

logger = logging.getLogger(__name__)


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    """
    Webhook endpoint management
    """
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'authentication_type', 'workflow']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get webhook endpoints for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return WebhookEndpoint.objects.filter(organization=organization).select_related('workflow')

    def get_serializer_class(self):
        """Dynamic serializer based on action"""
        if self.action == 'create':
            return WebhookEndpointCreateSerializer
        return WebhookEndpointSerializer

    def perform_create(self, serializer):
        """Create webhook endpoint with organization context"""
        organization = self.request.user.organization_memberships.first().organization

        # Generate unique URL path
        import secrets
        url_path = secrets.token_urlsafe(16)

        webhook = serializer.save(
            organization=organization,
            created_by=self.request.user,
            url_path=url_path
        )

        logger.info(f"Created webhook endpoint: {webhook.name} for {organization.name}")

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test webhook endpoint with sample data"""
        webhook = self.get_object()

        # Get test data from request
        test_data = request.data.get('test_data', {'message': 'Test webhook'})
        headers = request.data.get('headers', {})

        try:
            # Create test delivery
            delivery = WebhookDelivery.objects.create(
                webhook_endpoint=webhook,
                delivery_id=f"test-{uuid.uuid4().hex[:8]}",
                trigger_event='test',
                request_method='POST',
                request_headers=headers,
                request_body=json.dumps(test_data)
            )

            # Simulate webhook processing
            self._process_webhook_delivery(delivery, test_data, headers, test_mode=True)

            return Response({
                'message': 'Webhook test completed',
                'delivery_id': delivery.delivery_id,
                'status': delivery.status
            })

        except Exception as e:
            logger.error(f"Webhook test failed: {str(e)}")
            return Response(
                {'error': f'Webhook test failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def regenerate_secret(self, request, pk=None):
        """Regenerate webhook secret token"""
        webhook = self.get_object()

        # Check permissions
        if webhook.organization != request.user.organization_memberships.first().organization:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate new secret
        import secrets
        webhook.secret_token = secrets.token_urlsafe(32)
        webhook.save()

        return Response({
            'message': 'Secret token regenerated successfully',
            'new_secret': webhook.secret_token
        })

    @action(detail=True, methods=['get'])
    def deliveries(self, request, pk=None):
        """Get delivery history for webhook"""
        webhook = self.get_object()

        deliveries = WebhookDelivery.objects.filter(
            webhook_endpoint=webhook
        ).order_by('-created_at')[:50]  # Last 50 deliveries

        serializer = WebhookDeliverySerializer(deliveries, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get webhook statistics"""
        webhook = self.get_object()

        # Get time range
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)

        deliveries = WebhookDelivery.objects.filter(
            webhook_endpoint=webhook,
            created_at__gte=start_date
        )

        total_deliveries = deliveries.count()
        successful_deliveries = deliveries.filter(status='delivered').count()
        failed_deliveries = deliveries.filter(status='failed').count()

        # Calculate average response time
        delivered_deliveries = deliveries.filter(response_time_ms__isnull=False)
        avg_response_time = delivered_deliveries.aggregate(
            avg=Avg('response_time_ms')
        )['avg'] or 0

        return Response({
            'period_days': days,
            'total_deliveries': total_deliveries,
            'successful_deliveries': successful_deliveries,
            'failed_deliveries': failed_deliveries,
            'success_rate': (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0,
            'average_response_time_ms': round(avg_response_time, 2),
            'current_status': webhook.status
        })

    def _process_webhook_delivery(self, delivery, data, headers, test_mode=False):
        """Process webhook delivery (trigger workflow execution)"""
        try:
            webhook = delivery.webhook_endpoint

            if test_mode:
                # For test mode, just mark as delivered
                delivery.mark_delivered(200, 'Test successful', 50)
                return

            # Trigger workflow execution
            from apps.executions.models import ExecutionQueue

            execution = ExecutionQueue.objects.create(
                workflow=webhook.workflow,
                execution_id=f"webhook-{uuid.uuid4().hex[:8]}",
                trigger_type='webhook',
                trigger_data={
                    'webhook_id': str(webhook.id),
                    'delivery_id': delivery.delivery_id,
                    'headers': headers
                },
                input_data=data,
                priority='normal'
            )

            # Mark delivery as delivered
            delivery.mark_delivered(200, f'Workflow triggered: {execution.execution_id}', 100)

            logger.info(f"Webhook {webhook.name} triggered workflow execution: {execution.execution_id}")

        except Exception as e:
            logger.error(f"Error processing webhook delivery: {str(e)}")
            delivery.mark_failed(500, str(e))


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Webhook delivery history (read-only)
    """
    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'webhook_endpoint']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get webhook deliveries for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return WebhookDelivery.objects.filter(
            webhook_endpoint__organization=organization
        ).select_related('webhook_endpoint')

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry failed webhook delivery"""
        delivery = self.get_object()

        if not delivery.can_retry():
            return Response(
                {'error': 'Delivery cannot be retried'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create new delivery for retry
        new_delivery = WebhookDelivery.objects.create(
            webhook_endpoint=delivery.webhook_endpoint,
            delivery_id=f"retry-{uuid.uuid4().hex[:8]}",
            trigger_event=delivery.trigger_event,
            request_method=delivery.request_method,
            request_headers=delivery.request_headers,
            request_body=delivery.request_body,
            attempt_number=delivery.attempt_number + 1,
            max_attempts=delivery.max_attempts
        )

        # Process the retry
        try:
            data = json.loads(delivery.request_body)
            headers = delivery.request_headers
            self._process_webhook_delivery(new_delivery, data, headers)
        except Exception as e:
            new_delivery.mark_failed(500, str(e))

        return Response({
            'message': 'Delivery retry initiated',
            'new_delivery_id': new_delivery.delivery_id
        })


class WebhookEventViewSet(viewsets.ModelViewSet):
    """
    Webhook event management
    """
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['event_type', 'processed', 'webhook_endpoint']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get webhook events for current organization"""
        organization = self.request.user.organization_memberships.first().organization
        return WebhookEvent.objects.filter(
            webhook_endpoint__organization=organization
        ).select_related('webhook_endpoint')

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Manually process webhook event"""
        event = self.get_object()

        try:
            # Process the event
            result = self._process_webhook_event(event)

            event.mark_processed(result)

            return Response({
                'message': 'Event processed successfully',
                'result': result
            })

        except Exception as e:
            event.mark_processed(error=e)
            return Response(
                {'error': f'Failed to process event: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _process_webhook_event(self, event):
        """Process webhook event"""
        # This would contain the actual event processing logic
        # For now, just return a success result
        return {
            'status': 'success',
            'message': f'Processed {event.event_type} event',
            'timestamp': timezone.now().isoformat()
        }


class WebhookTemplateViewSet(viewsets.ModelViewSet):
    """
    Webhook template management
    """
    serializer_class = WebhookTemplateSerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['webhook_type', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get webhook templates"""
        # Show public templates and user's own templates
        return WebhookTemplate.objects.filter(
            Q(created_by=self.request.user) | Q(created_by__isnull=True)
        )

    def perform_create(self, serializer):
        """Create webhook template"""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def use_template(self, request, pk=None):
        """Create webhook endpoint from template"""
        template = self.get_object()

        # Get required data from request
        name = request.data.get('name')
        workflow_id = request.data.get('workflow_id')

        if not name or not workflow_id:
            return Response(
                {'error': 'Name and workflow_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            organization = request.user.organization_memberships.first().organization
            workflow = Workflow.objects.get(id=workflow_id, organization=organization)

            # Create webhook endpoint from template
            webhook = WebhookEndpoint.objects.create(
                organization=organization,
                workflow=workflow,
                created_by=request.user,
                name=name,
                description=f"Created from template: {template.name}",
                **template.default_config
            )

            # Generate URL path
            webhook.generate_url_path()
            webhook.save()

            # Increment template usage
            template.increment_usage()

            serializer = WebhookEndpointSerializer(webhook)
            return Response({
                'message': 'Webhook endpoint created from template',
                'webhook': serializer.data
            })

        except Workflow.DoesNotExist:
            return Response(
                {'error': 'Workflow not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to create webhook: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def webhook_receiver(request, url_path):
    """
    Receive webhook requests and trigger workflows
    """
    try:
        # Find webhook endpoint
        try:
            webhook = WebhookEndpoint.objects.get(
                url_path=url_path,
                status='active'
            )
        except WebhookEndpoint.DoesNotExist:
            logger.warning(f"Webhook not found: {url_path}")
            return JsonResponse({'error': 'Webhook not found'}, status=404)

        # Check allowed methods
        if webhook.allowed_methods and request.method not in webhook.allowed_methods:
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        # Check IP whitelist
        if webhook.allowed_ips:
            client_ip = _get_client_ip(request)
            if client_ip not in webhook.allowed_ips:
                logger.warning(f"IP not allowed for webhook {webhook.name}: {client_ip}")
                return JsonResponse({'error': 'IP not allowed'}, status=403)

        # Rate limiting
        if not _check_rate_limit(webhook, request):
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        # Authentication
        if not _authenticate_webhook_request(webhook, request):
            return JsonResponse({'error': 'Authentication failed'}, status=401)

        # Parse request body
        try:
            if webhook.data_format == 'json':
                data = json.loads(request.body.decode('utf-8')) if request.body else {}
            elif webhook.data_format == 'form':
                data = dict(request.POST)
            elif webhook.data_format == 'xml':
                # Basic XML parsing (would need more sophisticated parsing in production)
                data = {'xml_content': request.body.decode('utf-8')}
            else:  # raw
                data = {'raw_content': request.body.decode('utf-8')}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing webhook data: {str(e)}")
            return JsonResponse({'error': 'Invalid request format'}, status=400)

        # Create webhook delivery record
        delivery = WebhookDelivery.objects.create(
            webhook_endpoint=webhook,
            delivery_id=f"wh-{uuid.uuid4().hex[:8]}",
            trigger_event='webhook_received',
            request_method=request.method,
            request_headers=dict(request.headers),
            request_body=json.dumps(data)
        )

        # Process webhook (trigger workflow)
        try:
            _process_webhook_sync(delivery, data, dict(request.headers))

            # Update webhook statistics
            webhook.update_delivery_stats(success=True)

            return JsonResponse({
                'status': 'success',
                'message': 'Webhook received and processed',
                'delivery_id': delivery.delivery_id
            })

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            delivery.mark_failed(500, str(e))
            webhook.update_delivery_stats(success=False)

            return JsonResponse({
                'status': 'error',
                'message': 'Webhook processing failed',
                'delivery_id': delivery.delivery_id
            }, status=500)

    except Exception as e:
        logger.error(f"Unexpected error in webhook receiver: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def webhook_test(request, webhook_id):
    """
    Test webhook endpoint functionality
    """
    try:
        organization = request.user.organization_memberships.first().organization
        webhook = WebhookEndpoint.objects.get(
            id=webhook_id,
            organization=organization
        )
    except WebhookEndpoint.DoesNotExist:
        return Response(
            {'error': 'Webhook not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = WebhookTestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    test_data = serializer.validated_data['test_data']
    headers = serializer.validated_data['headers']

    try:
        # Create test delivery
        delivery = WebhookDelivery.objects.create(
            webhook_endpoint=webhook,
            delivery_id=f"test-{uuid.uuid4().hex[:8]}",
            trigger_event='test',
            request_method='POST',
            request_headers=headers,
            request_body=json.dumps(test_data)
        )

        # Process test webhook
        _process_webhook_sync(delivery, test_data, headers, test_mode=True)

        return Response({
            'status': 'success',
            'message': 'Webhook test completed successfully',
            'delivery_id': delivery.delivery_id,
            'response_time_ms': delivery.response_time_ms,
            'result': 'Test webhook execution successful'
        })

    except Exception as e:
        logger.error(f"Webhook test failed: {str(e)}")
        return Response(
            {'error': f'Webhook test failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def webhook_stats(request):
    """
    Get webhook statistics for organization
    """
    organization = request.user.organization_memberships.first().organization

    # Get time range
    days = int(request.query_params.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Get organization webhooks
    webhooks = WebhookEndpoint.objects.filter(organization=organization)

    # Get deliveries in time range
    deliveries = WebhookDelivery.objects.filter(
        webhook_endpoint__organization=organization,
        created_at__gte=start_date
    )

    # Calculate statistics
    total_endpoints = webhooks.count()
    active_endpoints = webhooks.filter(status='active').count()
    total_deliveries = deliveries.count()
    successful_deliveries = deliveries.filter(status='delivered').count()
    failed_deliveries = deliveries.filter(status='failed').count()

    success_rate = (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0

    # Average response time
    delivered_deliveries = deliveries.filter(response_time_ms__isnull=False)
    avg_response_time = delivered_deliveries.aggregate(
        avg=Avg('response_time_ms')
    )['avg'] or 0

    # Daily delivery trends
    daily_deliveries = []
    for i in range(days):
        date = (timezone.now() - timedelta(days=i)).date()
        day_deliveries = deliveries.filter(created_at__date=date)

        daily_deliveries.append({
            'date': date.isoformat(),
            'total': day_deliveries.count(),
            'successful': day_deliveries.filter(status='delivered').count(),
            'failed': day_deliveries.filter(status='failed').count()
        })

    # Top endpoints by delivery count
    top_endpoints = deliveries.values(
        'webhook_endpoint__name', 'webhook_endpoint__id'
    ).annotate(
        delivery_count=Count('id'),
        success_count=Count('id', filter=Q(status='delivered')),
        avg_response_time=Avg('response_time_ms')
    ).order_by('-delivery_count')[:10]

    stats = {
        'period_days': days,
        'total_endpoints': total_endpoints,
        'active_endpoints': active_endpoints,
        'total_deliveries': total_deliveries,
        'successful_deliveries': successful_deliveries,
        'failed_deliveries': failed_deliveries,
        'success_rate': round(success_rate, 2),
        'average_response_time': round(avg_response_time, 2),
        'daily_deliveries': daily_deliveries,
        'top_endpoints': list(top_endpoints)
    }

    serializer = WebhookStatsSerializer(stats)
    return Response(serializer.data)


# Helper functions

def _get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _check_rate_limit(webhook, request):
    """Check rate limiting for webhook"""
    client_ip = _get_client_ip(request)

    rate_limit, created = WebhookRateLimit.objects.get_or_create(
        webhook_endpoint=webhook,
        ip_address=client_ip
    )

    return rate_limit.check_rate_limit()


def _authenticate_webhook_request(webhook, request):
    """Authenticate webhook request based on configured method"""
    if webhook.authentication_type == 'none':
        return True

    elif webhook.authentication_type == 'secret':
        # Check secret token in header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        secret_header = request.META.get('HTTP_X_WEBHOOK_SECRET', '')

        return webhook.secret_token in [auth_header.replace('Bearer ', ''), secret_header]

    elif webhook.authentication_type == 'signature':
        # Verify HMAC signature
        signature_header = request.META.get(f'HTTP_{webhook.signature_header.upper().replace("-", "_")}', '')

        if not signature_header or not webhook.secret_token:
            return False

        # Verify signature
        payload = request.body.decode('utf-8')
        return webhook.verify_signature(payload, signature_header)

    elif webhook.authentication_type == 'basic':
        # Basic authentication (would need to implement)
        return True

    elif webhook.authentication_type == 'bearer':
        # Bearer token authentication
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        return auth_header.startswith('Bearer ') and webhook.secret_token in auth_header

    return False


def _process_webhook_sync(delivery, data, headers, test_mode=False):
    """Process webhook delivery synchronously"""
    start_time = timezone.now()

    try:
        webhook = delivery.webhook_endpoint

        if test_mode:
            # For test mode, simulate processing
            import time
            time.sleep(0.05)  # Simulate 50ms processing time
            delivery.mark_delivered(200, 'Test successful', 50)
            return

        # Create workflow execution
        from apps.executions.models import ExecutionQueue

        execution = ExecutionQueue.objects.create(
            workflow=webhook.workflow,
            execution_id=f"webhook-{uuid.uuid4().hex[:8]}",
            trigger_type='webhook',
            trigger_data={
                'webhook_id': str(webhook.id),
                'delivery_id': delivery.delivery_id,
                'headers': headers
            },
            input_data=data,
            priority='normal'
        )

        # Calculate response time
        end_time = timezone.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Mark delivery as successful
        delivery.mark_delivered(
            200,
            f'Workflow triggered: {execution.execution_id}',
            response_time_ms
        )

        logger.info(f"Webhook {webhook.name} triggered execution: {execution.execution_id}")

    except Exception as e:
        # Calculate response time even for errors
        end_time = timezone.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        delivery.mark_failed(500, str(e))
        logger.error(f"Error processing webhook {delivery.webhook_endpoint.name}: {str(e)}")
        raise