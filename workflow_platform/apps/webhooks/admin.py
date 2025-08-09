"""
Webhooks Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Avg
from django.utils import timezone
from .models import (
    WebhookEndpoint, WebhookDelivery, WebhookRateLimit,
    WebhookEvent, WebhookTemplate
)


class WebhookDeliveryInline(admin.TabularInline):
    """Inline for webhook deliveries"""
    model = WebhookDelivery
    extra = 0
    fields = ['status', 'response_status_code', 'response_time_ms', 'created_at']
    readonly_fields = ['response_status_code', 'response_time_ms', 'created_at']
    can_delete = False

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-created_at')[:10]


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    """Webhook endpoint admin"""

    list_display = [
        'name', 'organization', 'workflow', 'status', 'authentication_type',
        'delivery_count', 'success_rate_display', 'created_at'
    ]

    list_filter = [
        'status', 'authentication_type', 'data_format', 'created_at', 'organization'
    ]

    search_fields = [
        'name', 'description', 'url_path', 'organization__name', 'workflow__name'
    ]

    readonly_fields = [
        'url_path', 'created_at', 'updated_at', 'delivery_stats',
        'last_triggered_at', 'total_deliveries'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name', 'description', 'organization', 'workflow', 'status'
            )
        }),
        ('Endpoint Configuration', {
            'fields': (
                'url_path', 'allowed_methods', 'allowed_ips', 'custom_headers'
            )
        }),
        ('Authentication', {
            'fields': (
                'authentication_type', 'secret_token', 'signature_header'
            ),
            'classes': ('collapse',)
        }),
        ('Rate Limiting', {
            'fields': (
                'rate_limit_requests', 'rate_limit_window'
            ),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': (
                'data_format', 'timeout_seconds', 'retry_attempts', 'retry_delay'
            ),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': (
                'total_deliveries', 'successful_deliveries', 'failed_deliveries',
                'last_triggered_at', 'delivery_stats'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    inlines = [WebhookDeliveryInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'workflow', 'created_by'
        ).annotate(
            delivery_count=Count('deliveries')
        )

    def delivery_count(self, obj):
        """Display delivery count"""
        count = obj.delivery_count
        if count > 0:
            url = reverse('admin:webhooks_webhookdelivery_changelist')
            return format_html(
                '<a href="{}?webhook_endpoint={}">{}</a>',
                url, obj.id, count
            )
        return count

    delivery_count.short_description = 'Deliveries'
    delivery_count.admin_order_field = 'delivery_count'

    def success_rate_display(self, obj):
        """Display success rate with color coding"""
        if obj.total_deliveries > 0:
            rate = (obj.successful_deliveries / obj.total_deliveries) * 100
            if rate >= 95:
                color = 'green'
            elif rate >= 80:
                color = 'orange'
            else:
                color = 'red'

            return format_html(
                '<span style="color: {};">{:.1f}%</span>',
                color, rate
            )
        return 'No deliveries'

    success_rate_display.short_description = 'Success Rate'

    def delivery_stats(self, obj):
        """Display delivery statistics"""
        return format_html(
            'Total: {}<br>Successful: {}<br>Failed: {}',
            obj.total_deliveries,
            obj.successful_deliveries,
            obj.failed_deliveries
        )

    delivery_stats.short_description = 'Delivery Statistics'


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    """Webhook delivery admin"""

    list_display = [
        'webhook_endpoint', 'status', 'response_status_code',
        'response_time_display', 'attempt_number', 'created_at'
    ]

    list_filter = [
        'status', 'response_status_code', 'attempt_number', 'created_at'
    ]

    search_fields = [
        'webhook_endpoint__name', 'delivery_id', 'trigger_event'
    ]

    readonly_fields = [
        'delivery_id', 'created_at', 'sent_at', 'response_time_ms',
        'request_headers', 'response_headers'
    ]

    fieldsets = (
        ('Delivery Information', {
            'fields': (
                'webhook_endpoint', 'delivery_id', 'status', 'trigger_event'
            )
        }),
        ('Request Details', {
            'fields': (
                'request_method', 'request_headers', 'request_body'
            ),
            'classes': ('collapse',)
        }),
        ('Response Details', {
            'fields': (
                'response_status_code', 'response_headers', 'response_body',
                'response_time_ms'
            ),
            'classes': ('collapse',)
        }),
        ('Retry Information', {
            'fields': (
                'attempt_number', 'max_attempts', 'next_retry_at'
            ),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('created_at', 'sent_at'),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('webhook_endpoint')

    def response_time_display(self, obj):
        """Display response time with formatting"""
        if obj.response_time_ms:
            if obj.response_time_ms < 1000:
                return f"{obj.response_time_ms}ms"
            else:
                return f"{obj.response_time_ms / 1000:.1f}s"
        return "-"

    response_time_display.short_description = 'Response Time'
    response_time_display.admin_order_field = 'response_time_ms'

    # Limit records by default for performance
    def changelist_view(self, request, extra_context=None):
        if not request.GET.get('created_at__gte'):
            from datetime import timedelta
            seven_days_ago = timezone.now() - timedelta(days=7)
            request.GET = request.GET.copy()
            request.GET['created_at__gte'] = seven_days_ago.strftime('%Y-%m-%d')

        return super().changelist_view(request, extra_context)


@admin.register(WebhookRateLimit)
class WebhookRateLimitAdmin(admin.ModelAdmin):
    """Webhook rate limit admin"""

    list_display = [
        'webhook_endpoint', 'ip_address', 'request_count',
        'window_start', 'is_blocked'
    ]

    list_filter = ['is_blocked', 'window_start']

    search_fields = [
        'webhook_endpoint__name', 'ip_address'
    ]

    readonly_fields = ['window_start', 'created_at', 'updated_at']

    fieldsets = (
        ('Rate Limit Information', {
            'fields': (
                'webhook_endpoint', 'ip_address', 'request_count', 'is_blocked'
            )
        }),
        ('Timing', {
            'fields': ('window_start', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('webhook_endpoint')


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    """Webhook event admin"""

    list_display = [
        'name', 'webhook_endpoint', 'event_type', 'processed',
        'processing_time_display', 'created_at'
    ]

    list_filter = [
        'event_type', 'processed', 'created_at'
    ]

    search_fields = [
        'name', 'webhook_endpoint__name', 'event_data'
    ]

    readonly_fields = [
        'created_at', 'processed_at', 'processing_time', 'processing_result'
    ]

    fieldsets = (
        ('Event Information', {
            'fields': (
                'webhook_endpoint', 'name', 'event_type', 'processed'
            )
        }),
        ('Event Data', {
            'fields': ('event_data', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': (
                'processed_at', 'processing_time', 'processing_result'
            ),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        })
    )

    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('webhook_endpoint')

    def processing_time_display(self, obj):
        """Display processing time with formatting"""
        if obj.processing_time:
            seconds = obj.processing_time.total_seconds()
            if seconds < 1:
                return f"{seconds * 1000:.0f}ms"
            else:
                return f"{seconds:.2f}s"
        return "-"

    processing_time_display.short_description = 'Processing Time'
    processing_time_display.admin_order_field = 'processing_time'


@admin.register(WebhookTemplate)
class WebhookTemplateAdmin(admin.ModelAdmin):
    """Webhook template admin"""

    list_display = [
        'name', 'webhook_type', 'is_active', 'usage_count',
        'created_by', 'created_at'
    ]

    list_filter = ['webhook_type', 'is_active', 'created_at']

    search_fields = ['name', 'description', 'webhook_type']

    readonly_fields = ['usage_count', 'created_at', 'updated_at']

    fieldsets = (
        ('Template Information', {
            'fields': (
                'name', 'description', 'webhook_type', 'is_active'
            )
        }),
        ('Configuration', {
            'fields': ('default_config', 'example_payload'),
            'classes': ('collapse',)
        }),
        ('Documentation', {
            'fields': ('setup_instructions', 'validation_rules'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'usage_count', 'created_by', 'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')