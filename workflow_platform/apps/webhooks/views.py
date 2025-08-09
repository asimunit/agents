"""
Webhook Views - Advanced webhook handling and management
"""
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.conf import settings
import json
import asyncio
import logging

from .models import (
    WebhookEndpoint, WebhookDelivery, WebhookRateLimit,
    WebhookEvent, WebhookTemplate
)
from .serializers import (
    WebhookEndpointSerializer, WebhookDeliverySerializer,
    WebhookEventSerializer, WebhookTemplateSerializer,
    WebhookEndpointCreateSerializer
)
from apps.core.permissions import OrganizationPermission
from apps.core.pagination import CustomPageNumberPagination
from apps.core.workflow_engine import workflow_engine

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

        # Log event
        WebhookEvent.objects.create(
            organization=organization,
            webhook_endpoint=webhook,
            event_type='endpoint_created',
            description=f'Webhook endpoint "{webhook.name}" created',
            user=self.request.user,
            ip_address=self._get_client_ip(self.request),
            event_data={'webhook_id': str(webhook.id)}
        )

    def perform_update(self, serializer):
        """Update webhook endpoint with logging"""
        webhook = serializer.save()

        # Log event
        WebhookEvent.objects.create(
            organization=webhook.organization,
            webhook_endpoint=webhook,
            event_type='endpoint_updated',
            description=f'Webhook endpoint "{webhook.name}" updated',
            user=self.request.user,
            ip_address=self._get_client_ip(self.request),
            event_data={'webhook_id': str(webhook.id)}
        )

    def perform_destroy(self, instance):
        """Delete webhook endpoint with logging"""
        WebhookEvent.objects.create(
            organization=instance.organization,
            webhook_endpoint=instance,
            event_type='endpoint_deleted',
            description=f'Webhook endpoint "{instance.name}" deleted',
            user=self.request.user,
            ip_address=self._get_client_ip(self.request),
            event_data={'webhook_id': str(instance.id)}
        )

        super().perform_destroy(instance)

    @action(detail=True, methods=['get'])
    def deliveries(self, request, pk=None):
        """Get webhook deliveries"""
        webhook = self.get_object()

        deliveries = webhook.deliveries.all()

        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            deliveries = deliveries.filter(status=status_filter)

        days = request.query_params.get('days', 7)
        if days:
            start_date = timezone.now() - timezone.timedelta(days=int(days))
            deliveries = deliveries.filter(received_at__gte=start_date)

        # Paginate
        page = self.paginate_queryset(deliveries)
        if page is not None:
            serializer = WebhookDeliverySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = WebhookDeliverySerializer(deliveries, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get webhook analytics"""
        webhook = self.get_object()

        # Date range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timezone.timedelta(days=days)

        # Get deliveries in date range
        deliveries = webhook.deliveries.filter(received_at__gte=start_date)

        # Basic metrics
        total_deliveries = deliveries.count()
        successful_deliveries = deliveries.filter(status='success').count()
        failed_deliveries = deliveries.filter(status='failed').count()

        success_rate = (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0

        # Average processing time
        avg_processing_time = deliveries.filter(
            status='success',
            processing_time_ms__isnull=False
        ).aggregate(avg_time=Avg('processing_time_ms'))['avg_time'] or 0

        # Daily delivery counts
        daily_stats = []
        for i in range(days):
            date = (timezone.now() - timezone.timedelta(days=i)).date()
            day_deliveries = deliveries.filter(received_at__date=date)

            daily_stats.append({
                'date': date.isoformat(),
                'total': day_deliveries.count(),
                'successful': day_deliveries.filter(status='success').count(),
                'failed': day_deliveries.filter(status='failed').count(),
            })

        # Error analysis
        error_types = deliveries.filter(status='failed').values(
            'error_message'
        ).annotate(count=Count('id')).order_by('-count')[:5]

        # IP address statistics
        top_ips = deliveries.values('ip_address').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        analytics_data = {
            'overview': {
                'total_deliveries': total_deliveries,
                'successful_deliveries': successful_deliveries,
                'failed_deliveries': failed_deliveries,
                'success_rate': round(success_rate, 2),
                'average_processing_time': round(avg_processing_time, 2) if avg_processing_time else 0,
            },
            'daily_stats': daily_stats,
            'error_analysis': list(error_types),
            'top_source_ips': list(top_ips),
        }

        return Response(analytics_data)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test webhook endpoint with sample data"""
        webhook = self.get_object()

        # Create test payload
        test_payload = request.data.get('payload', {
            'test': True,
            'timestamp': timezone.now().isoformat(),
            'message': 'This is a test webhook delivery'
        })

        try:
            # Execute workflow with test data
            execution = asyncio.run(
                workflow_engine.execute_workflow(
                    workflow=webhook.workflow,
                    input_data=test_payload,
                    triggered_by_user_id=request.user.id,
                    trigger_source='webhook_test'
                )
            )

            return Response({
                'success': True,
                'execution_id': execution.id,
                'message': 'Test webhook executed successfully'
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def regenerate_url(self, request, pk=None):
        """Regenerate webhook URL"""
        webhook = self.get_object()

        # Generate new URL path
        import secrets
        old_url_path = webhook.url_path
        webhook.url_path = secrets.token_urlsafe(16)
        webhook.save()

        # Log event
        WebhookEvent.objects.create(
            organization=webhook.organization,
            webhook_endpoint=webhook,
            event_type='endpoint_updated',
            description=f'Webhook URL regenerated for "{webhook.name}"',
            user=request.user,
            ip_address=self._get_client_ip(request),
            event_data={
                'webhook_id': str(webhook.id),
                'old_url_path': old_url_path,
                'new_url_path': webhook.url_path
            }
        )

        return Response({
            'new_url': webhook.full_url,
            'url_path': webhook.url_path
        })

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH"])
def webhook_receiver(request, url_path):
    """
    Webhook receiver endpoint - handles incoming webhook requests
    """

    try:
        # Get webhook endpoint
        try:
            webhook = WebhookEndpoint.objects.get(url_path=url_path, status='active')
        except WebhookEndpoint.DoesNotExist:
            logger.warning(f"Webhook not found: {url_path}")
            return HttpResponse('Webhook not found', status=404)

        # Get client information
        client_ip = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Check IP whitelist
        if not webhook.is_ip_allowed(client_ip):
            logger.warning(f"IP {client_ip} not allowed for webhook {webhook.name}")

            # Log blocked event
            WebhookEvent.objects.create(
                organization=webhook.organization,
                webhook_endpoint=webhook,
                event_type='ip_blocked',
                description=f'Request from blocked IP: {client_ip}',
                ip_address=client_ip,
                user_agent=user_agent
            )

            return HttpResponse('IP not allowed', status=403)

        # Check rate limiting
        rate_limit, created = WebhookRateLimit.objects.get_or_create(
            webhook_endpoint=webhook,
            ip_address=client_ip
        )

        if rate_limit.is_rate_limited():
            logger.warning(f"Rate limit exceeded for IP {client_ip} on webhook {webhook.name}")

            # Log rate limit event
            WebhookEvent.objects.create(
                organization=webhook.organization,
                webhook_endpoint=webhook,
                event_type='rate_limit_hit',
                description=f'Rate limit exceeded for IP: {client_ip}',
                ip_address=client_ip,
                user_agent=user_agent
            )

            return HttpResponse('Rate limit exceeded', status=429)

        rate_limit.increment_request()

        # Check HTTP method
        if webhook.allowed_methods and request.method not in webhook.allowed_methods:
            return HttpResponse('Method not allowed', status=405)

        # Get request headers
        headers = {}
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').title()
                headers[header_name] = value

        # Check required custom headers
        for required_header, required_value in webhook.custom_headers.items():
            if headers.get(required_header) != required_value:
                return HttpResponse('Invalid headers', status=400)

        # Get payload
        try:
            if webhook.data_format == 'json':
                payload = json.loads(request.body.decode('utf-8')) if request.body else {}
                raw_payload = request.body.decode('utf-8')
            elif webhook.data_format == 'form':
                payload = dict(request.POST)
                raw_payload = request.body.decode('utf-8')
            elif webhook.data_format == 'xml':
                # For XML, store as raw and let workflow process it
                payload = {'xml_data': request.body.decode('utf-8')}
                raw_payload = request.body.decode('utf-8')
            else:  # raw
                payload = {'raw_data': request.body.decode('utf-8')}
                raw_payload = request.body.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to parse payload for webhook {webhook.name}: {str(e)}")
            return HttpResponse('Invalid payload format', status=400)

        # Authentication
        if webhook.authentication_type == 'secret':
            auth_header = headers.get('Authorization', '')
            if not auth_header.startswith('Bearer ') or auth_header[7:] != webhook.secret_token:
                # Log authentication failure
                WebhookEvent.objects.create(
                    organization=webhook.organization,
                    webhook_endpoint=webhook,
                    event_type='authentication_failed',
                    description='Invalid secret token',
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                return HttpResponse('Authentication failed', status=401)

        elif webhook.authentication_type == 'signature':
            signature = headers.get(webhook.signature_header, '')
            if not webhook.verify_signature(request.body, signature):
                # Log authentication failure
                WebhookEvent.objects.create(
                    organization=webhook.organization,
                    webhook_endpoint=webhook,
                    event_type='authentication_failed',
                    description='Invalid signature',
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                return HttpResponse('Authentication failed', status=401)

        elif webhook.authentication_type == 'basic':
            # Implement basic auth if needed
            pass

        elif webhook.authentication_type == 'bearer':
            auth_header = headers.get('Authorization', '')
            if not auth_header.startswith('Bearer ') or auth_header[7:] != webhook.secret_token:
                return HttpResponse('Authentication failed', status=401)

        # Create delivery record
        delivery = WebhookDelivery.objects.create(
            webhook_endpoint=webhook,
            http_method=request.method,
            headers=headers,
            payload=payload,
            raw_payload=raw_payload,
            ip_address=client_ip,
            user_agent=user_agent,
            status='pending'
        )

        # Log delivery received event
        WebhookEvent.objects.create(
            organization=webhook.organization,
            webhook_endpoint=webhook,
            delivery=delivery,
            event_type='delivery_received',
            description=f'Webhook delivery received from {client_ip}',
            ip_address=client_ip,
            user_agent=user_agent
        )

        # Process webhook asynchronously
        try:
            # Add webhook-specific data to payload
            enhanced_payload = {
                **payload,
                '_webhook': {
                    'endpoint_id': str(webhook.id),
                    'endpoint_name': webhook.name,
                    'delivery_id': str(delivery.id),
                    'source_ip': client_ip,
                    'user_agent': user_agent,
                    'received_at': delivery.received_at.isoformat(),
                    'headers': headers
                }
            }

            # Execute workflow
            delivery.mark_processing()

            execution = asyncio.run(
                workflow_engine.execute_workflow(
                    workflow=webhook.workflow,
                    input_data=enhanced_payload,
                    triggered_by_user_id=None,  # System trigger
                    trigger_source='webhook'
                )
            )

            # Mark delivery as successful
            delivery.mark_success(execution.id)
            webhook.increment_stats(success=True)

            # Log success event
            WebhookEvent.objects.create(
                organization=webhook.organization,
                webhook_endpoint=webhook,
                delivery=delivery,
                event_type='delivery_processed',
                description='Webhook processed successfully',
                ip_address=client_ip,
                event_data={'execution_id': str(execution.id)}
            )

            return HttpResponse('OK', status=200)

        except Exception as e:
            # Mark delivery as failed
            delivery.mark_failed(str(e))
            webhook.increment_stats(success=False)

            # Log failure event
            WebhookEvent.objects.create(
                organization=webhook.organization,
                webhook_endpoint=webhook,
                delivery=delivery,
                event_type='delivery_failed',
                description=f'Webhook processing failed: {str(e)}',
                ip_address=client_ip,
                event_data={'error': str(e)}
            )

            logger.error(f"Webhook processing failed for {webhook.name}: {str(e)}")

            # Return 200 to prevent retries for application errors
            # Return 500 for system errors to trigger retries
            if 'timeout' in str(e).lower():
                return HttpResponse('Processing timeout', status=504)
            else:
                return HttpResponse('Processing failed', status=200)

    except Exception as e:
        logger.error(f"Webhook receiver error: {str(e)}")
        return HttpResponse('Internal server error', status=500)


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Webhook delivery management
    """
    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAuthenticated, OrganizationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'webhook_endpoint']
    ordering = ['-received_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Get deliveries for organization webhooks"""
        organization = self.request.user.organization_memberships.first().organization
        return WebhookDelivery.objects.filter(
            webhook_endpoint__organization=organization
        ).select_related('webhook_endpoint')

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry failed webhook delivery"""
        delivery = self.get_object()

        if delivery.status != 'failed':
            return Response(
                {'error': 'Can only retry failed deliveries'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Execute workflow with original payload
            execution = asyncio.run(
                workflow_engine.execute_workflow(
                    workflow=delivery.webhook_endpoint.workflow,
                    input_data=delivery.payload,
                    triggered_by_user_id=request.user.id,
                    trigger_source='webhook_retry'
                )
            )

            # Create new delivery record for retry
            retry_delivery = WebhookDelivery.objects.create(
                webhook_endpoint=delivery.webhook_endpoint,
                http_method=delivery.http_method,
                headers=delivery.headers,
                payload=delivery.payload,
                raw_payload=delivery.raw_payload,
                ip_address=delivery.ip_address,
                user_agent=delivery.user_agent,
                status='success',
                workflow_execution_id=execution.id,
                retry_count=delivery.retry_count + 1
            )

            retry_delivery.mark_success(execution.id)

            return Response({
                'success': True,
                'retry_delivery_id': retry_delivery.id,
                'execution_id': execution.id
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class WebhookTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Webhook template management
    """
    queryset = WebhookTemplate.objects.all()
    serializer_class = WebhookTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category', 'service_name', 'is_featured']
    ordering = ['-is_featured', '-usage_count']

    @action(detail=True, methods=['post'])
    def use_template(self, request, pk=None):
        """Create webhook endpoint from template"""
        template = self.get_object()
        organization = request.user.organization_memberships.first().organization

        # Get workflow ID from request
        workflow_id = request.data.get('workflow_id')
        if not workflow_id:
            return Response(
                {'error': 'workflow_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from apps.workflows.models import Workflow
            workflow = Workflow.objects.get(id=workflow_id, organization=organization)
        except Workflow.DoesNotExist:
            return Response(
                {'error': 'Workflow not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create webhook endpoint from template
        import secrets

        webhook_data = template.configuration.copy()
        webhook_data.update({
            'name': f"{template.service_name} Webhook",
            'description': template.description,
            'workflow': workflow,
        })

        webhook = WebhookEndpoint.objects.create(
            organization=organization,
            workflow=workflow,
            url_path=secrets.token_urlsafe(16),
            created_by=request.user,
            **webhook_data
        )

        # Increment template usage
        template.increment_usage()

        serializer = WebhookEndpointSerializer(webhook)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@api_view(['GET'])
@permission_classes([AllowAny])
def webhook_health_check(request):
    """Health check for webhook system"""

    try:
        # Check webhook system health
        active_webhooks = WebhookEndpoint.objects.filter(status='active').count()
        total_deliveries_today = WebhookDelivery.objects.filter(
            received_at__date=timezone.now().date()
        ).count()

        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now(),
            'active_webhooks': active_webhooks,
            'deliveries_today': total_deliveries_today
        }

        return Response(health_status)

    except Exception as e:
        return Response(
            {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': timezone.now()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )