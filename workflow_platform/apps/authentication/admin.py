"""
Authentication Admin Configuration
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from apps.organizations.models import OrganizationMember, OrganizationInvitation


class OrganizationMemberInline(admin.TabularInline):
    """Inline for organization memberships"""
    model = OrganizationMember
    fk_name = 'user'  # Specify which foreign key to use (user vs invited_by)
    extra = 0
    fields = ['organization', 'role', 'status', 'joined_at']
    readonly_fields = ['joined_at']


class CustomUserAdmin(BaseUserAdmin):
    """Enhanced User admin with organization info"""

    inlines = [OrganizationMemberInline]

    list_display = [
        'username', 'email', 'first_name', 'last_name',
        'is_active', 'is_staff', 'date_joined', 'organization_count'
    ]

    list_filter = tuple(BaseUserAdmin.list_filter) + ('organization_memberships__role',)

    search_fields = ['username', 'email', 'first_name', 'last_name']

    def organization_count(self, obj):
        """Display number of organizations user belongs to"""
        count = obj.organization_memberships.count()
        if count > 0:
            url = reverse('admin:organizations_organizationmember_changelist')
            return format_html(
                '<a href="{}?user={}">{} organization{}</a>',
                url, obj.id, count, 's' if count != 1 else ''
            )
        return '0'

    organization_count.short_description = 'Organizations'


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    """Organization invitation admin"""

    list_display = [
        'email', 'organization', 'role', 'status',
        'invited_by', 'created_at', 'expires_at'
    ]

    list_filter = ['status', 'role', 'created_at', 'expires_at']

    search_fields = ['email', 'organization__name', 'invited_by__username']

    readonly_fields = ['token', 'created_at']

    fieldsets = (
        ('Invitation Details', {
            'fields': ('organization', 'email', 'role', 'status')
        }),
        ('Metadata', {
            'fields': ('invited_by', 'token', 'expires_at', 'created_at', 'accepted_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'invited_by'
        )


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)