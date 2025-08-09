"""
Organizations Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import (
    Organization, OrganizationMember, OrganizationInvitation,
    OrganizationAPIKey, OrganizationUsage
)


class OrganizationMemberInline(admin.TabularInline):
    """Inline for organization members"""
    model = OrganizationMember
    extra = 0
    fields = ['user', 'role', 'status', 'joined_at']
    readonly_fields = ['joined_at']


class OrganizationAPIKeyInline(admin.TabularInline):
    """Inline for organization API keys"""
    model = OrganizationAPIKey
    extra = 0
    fields = ['name', 'is_active', 'expires_at', 'last_used_at']
    readonly_fields = ['last_used_at']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Organization admin"""

    list_display = [
        'name', 'slug', 'plan', 'status', 'member_count',
        'workflow_count', 'created_by', 'created_at'
    ]

    list_filter = ['plan', 'status', 'created_at']

    search_fields = ['name', 'slug', 'created_by__username']

    readonly_fields = ['created_at', 'updated_at', 'usage_stats']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'logo', 'website')
        }),
        ('Plan & Billing', {
            'fields': ('plan', 'status', 'max_workflows', 'max_executions_per_month', 'max_users')
        }),
        ('Customization', {
            'fields': ('primary_color', 'settings'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at', 'usage_stats'),
            'classes': ('collapse',)
        })
    )

    inlines = [OrganizationMemberInline, OrganizationAPIKeyInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').annotate(
            member_count=Count('members'),
            workflow_count=Count('workflows')
        )

    def member_count(self, obj):
        """Display member count"""
        count = obj.member_count
        url = reverse('admin:organizations_organizationmember_changelist')
        return format_html(
            '<a href="{}?organization={}">{}</a>',
            url, obj.id, count
        )

    member_count.short_description = 'Members'
    member_count.admin_order_field = 'member_count'

    def workflow_count(self, obj):
        """Display workflow count"""
        count = obj.workflow_count
        if count > 0:
            return format_html('<strong>{}</strong>', count)
        return count

    workflow_count.short_description = 'Workflows'
    workflow_count.admin_order_field = 'workflow_count'

    def usage_stats(self, obj):
        """Display usage statistics"""
        try:
            usage = OrganizationUsage.objects.filter(organization=obj).latest('date')
            return format_html(
                'Workflows: {}/{}<br>Executions: {}/{}<br>Users: {}/{}',
                usage.workflow_count, obj.max_workflows,
                usage.execution_count, obj.max_executions_per_month,
                usage.user_count, obj.max_users
            )
        except OrganizationUsage.DoesNotExist:
            return "No usage data"

    usage_stats.short_description = 'Usage Statistics'


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    """Organization member admin"""

    list_display = [
        'user', 'organization', 'role', 'status',
        'invited_by', 'joined_at'
    ]

    list_filter = ['role', 'status', 'joined_at']

    search_fields = [
        'user__username', 'user__email', 'organization__name'
    ]

    readonly_fields = ['invitation_token', 'invited_at', 'joined_at', 'created_at', 'updated_at']

    fieldsets = (
        ('Member Information', {
            'fields': ('organization', 'user', 'role', 'status')
        }),
        ('Permissions', {
            'fields': ('permissions',),
            'classes': ('collapse',)
        }),
        ('Invitation Details', {
            'fields': ('invited_by', 'invitation_token', 'invited_at', 'joined_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'organization', 'invited_by'
        )


@admin.register(OrganizationAPIKey)
class OrganizationAPIKeyAdmin(admin.ModelAdmin):
    """Organization API key admin"""

    list_display = [
        'name', 'organization', 'is_active', 'usage_count',
        'last_used_at', 'expires_at', 'created_by'
    ]

    list_filter = ['is_active', 'created_at', 'expires_at']

    search_fields = ['name', 'organization__name', 'created_by__username']

    readonly_fields = ['key', 'usage_count', 'last_used_at', 'created_at']

    fieldsets = (
        ('API Key Information', {
            'fields': ('name', 'organization', 'description', 'is_active')
        }),
        ('Access Control', {
            'fields': ('scopes', 'rate_limit_requests', 'allowed_ips')
        }),
        ('Security', {
            'fields': ('key', 'expires_at'),
            'classes': ('collapse',)
        }),
        ('Usage Statistics', {
            'fields': ('usage_count', 'last_used_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'created_by'
        )


@admin.register(OrganizationUsage)
class OrganizationUsageAdmin(admin.ModelAdmin):
    """Organization usage tracking admin"""

    list_display = [
        'organization', 'date', 'workflow_count', 'execution_count',
        'user_count', 'api_calls_count'
    ]

    list_filter = ['date', 'organization__plan']

    search_fields = ['organization__name']

    readonly_fields = ['created_at']

    date_hierarchy = 'date'

    fieldsets = (
        ('Usage Statistics', {
            'fields': (
                'organization', 'date', 'workflow_count', 'execution_count',
                'user_count', 'api_calls_count', 'storage_used_mb'
            )
        }),
        ('Breakdown', {
            'fields': ('usage_breakdown',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('organization')


# Custom admin site branding
admin.site.site_header = "Workflow Platform Administration"
admin.site.site_title = "Workflow Platform Admin"
admin.site.index_title = "Platform Management"