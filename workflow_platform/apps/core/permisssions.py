"""
Custom Permissions for Workflow Platform
"""
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.db.models import Q, Count


class OrganizationPermission(BasePermission):
    """
    Permission class that ensures user belongs to an organization
    and has appropriate access to resources
    """

    def has_permission(self, request, view):
        """Check if user has basic organization access"""
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user belongs to an organization
        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            # Store organization in request for later use
            request.organization = membership.organization
            request.user_role = membership.role

            return True

        except Exception:
            return False

    def has_object_permission(self, request, view, obj):
        """Check if user has access to specific object"""
        if not hasattr(request, 'organization'):
            return False

        # Check if object belongs to user's organization
        if hasattr(obj, 'organization'):
            return obj.organization == request.organization

        # For workflow-related objects, check through workflow
        if hasattr(obj, 'workflow'):
            return obj.workflow.organization == request.organization

        # For execution-related objects, check through execution
        if hasattr(obj, 'execution'):
            return obj.execution.workflow.organization == request.organization

        # For webhook-related objects, check through webhook_endpoint
        if hasattr(obj, 'webhook_endpoint'):
            return obj.webhook_endpoint.organization == request.organization

        return True


class WorkflowPermission(BasePermission):
    """
    Permission class for workflow-specific operations
    """

    def has_permission(self, request, view):
        """Check basic workflow permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            # Check specific workflow permissions based on action
            action = getattr(view, 'action', None)

            if action in ['create']:
                return self._can_create_workflow(membership)
            elif action in ['update', 'partial_update', 'destroy']:
                return self._can_modify_workflow(membership)
            elif action in ['execute']:
                return self._can_execute_workflow(membership)
            else:
                return True  # Allow read operations

        except Exception:
            return False

    def has_object_permission(self, request, view, obj):
        """Check object-specific workflow permissions"""
        if not hasattr(request, 'organization'):
            return False

        # Check if workflow belongs to organization
        if obj.organization != request.organization:
            return False

        # Check specific permissions based on action
        action = getattr(view, 'action', None)
        membership = request.user.organization_memberships.filter(
            organization=request.organization,
            status='active'
        ).first()

        if action in ['update', 'partial_update', 'destroy']:
            # Check if user can modify this specific workflow
            return self._can_modify_specific_workflow(membership, obj)
        elif action == 'execute':
            # Check if user can execute this specific workflow
            return self._can_execute_specific_workflow(membership, obj)

        return True

    def _can_create_workflow(self, membership):
        """Check if user can create workflows"""
        return membership.role in ['owner', 'admin', 'member']

    def _can_modify_workflow(self, membership):
        """Check if user can modify workflows"""
        return membership.role in ['owner', 'admin', 'member']

    def _can_execute_workflow(self, membership):
        """Check if user can execute workflows"""
        return membership.role in ['owner', 'admin', 'member']

    def _can_modify_specific_workflow(self, membership, workflow):
        """Check if user can modify specific workflow"""
        # Owners and admins can modify any workflow
        if membership.role in ['owner', 'admin']:
            return True

        # Members can modify workflows they created
        if membership.role == 'member':
            return workflow.created_by == membership.user

        return False

    def _can_execute_specific_workflow(self, membership, workflow):
        """Check if user can execute specific workflow"""
        # All members can execute active workflows
        return workflow.status == 'active'


class NodePermission(BasePermission):
    """
    Permission class for node-specific operations
    """

    def has_permission(self, request, view):
        """Check basic node permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            # Check node-specific permissions
            action = getattr(view, 'action', None)

            if action in ['create']:
                return self._can_create_nodes(membership)
            elif action in ['update', 'partial_update', 'destroy']:
                return self._can_modify_nodes(membership)

            return True

        except Exception:
            return False

    def _can_create_nodes(self, membership):
        """Check if user can create custom nodes"""
        return membership.role in ['owner', 'admin']

    def _can_modify_nodes(self, membership):
        """Check if user can modify nodes"""
        return membership.role in ['owner', 'admin']


class WebhookPermission(BasePermission):
    """
    Permission class for webhook-specific operations
    """

    def has_permission(self, request, view):
        """Check basic webhook permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            return True

        except Exception:
            return False

    def has_object_permission(self, request, view, obj):
        """Check object-specific webhook permissions"""
        if not hasattr(request, 'organization'):
            return False

        return obj.organization == request.organization


class AnalyticsPermission(BasePermission):
    """
    Permission class for analytics and reporting
    """

    def has_permission(self, request, view):
        """Check analytics permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            # Check if user can access analytics
            return self._can_access_analytics(membership)

        except Exception:
            return False

    def _can_access_analytics(self, membership):
        """Check if user can access analytics"""
        # All users can view basic analytics
        return True


class AdminPermission(BasePermission):
    """
    Permission class for admin-only operations
    """

    def has_permission(self, request, view):
        """Check admin permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            return membership.role in ['owner', 'admin']

        except Exception:
            return False


class OwnerPermission(BasePermission):
    """
    Permission class for owner-only operations
    """

    def has_permission(self, request, view):
        """Check owner permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            membership = request.user.organization_memberships.filter(status='active').first()
            if not membership:
                return False

            request.organization = membership.organization
            request.user_role = membership.role

            return membership.role == 'owner'

        except Exception:
            return False


class SharedWorkflowPermission(BasePermission):
    """
    Permission class for shared workflow access
    """

    def has_object_permission(self, request, view, obj):
        """Check if user has access to shared workflow"""
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if workflow is public
        if obj.is_public:
            return True

        # Check if user is in the organization
        if hasattr(request, 'organization') and obj.organization == request.organization:
            return True

        # Check if workflow is explicitly shared with user
        from apps.workflows.models import WorkflowShare

        try:
            share = WorkflowShare.objects.get(
                workflow=obj,
                shared_with=request.user
            )

            # Check permission level for specific actions
            action = getattr(view, 'action', None)

            if action in ['update', 'partial_update', 'destroy']:
                return share.permission in ['edit', 'admin']
            elif action == 'execute':
                return share.permission in ['execute', 'edit', 'admin']
            else:
                return True  # View permission

        except WorkflowShare.DoesNotExist:
            return False


class APIKeyPermission(BasePermission):
    """
    Permission class for API key authentication
    """

    def has_permission(self, request, view):
        """Check API key permissions"""
        # Check for API key in headers
        api_key = request.META.get('HTTP_X_API_KEY') or request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ',
                                                                                                           '')

        if not api_key:
            return False

        try:
            from apps.organizations.models import OrganizationAPIKey

            api_key_obj = OrganizationAPIKey.objects.get(
                key=api_key,
                is_active=True
            )

            # Check if API key is expired
            if api_key_obj.expires_at and api_key_obj.expires_at < timezone.now():
                return False

            # Store organization and API key for later use
            request.organization = api_key_obj.organization
            request.api_key = api_key_obj

            # Update last used timestamp
            api_key_obj.last_used_at = timezone.now()
            api_key_obj.save(update_fields=['last_used_at'])

            return True

        except OrganizationAPIKey.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        """Check API key object permissions"""
        if not hasattr(request, 'api_key'):
            return False

        # Check scopes
        action = getattr(view, 'action', None)
        required_scope = self._get_required_scope(view, action)

        if required_scope and required_scope not in request.api_key.scopes:
            return False

        # Check if object belongs to API key's organization
        if hasattr(obj, 'organization'):
            return obj.organization == request.organization

        return True

    def _get_required_scope(self, view, action):
        """Get required scope for view action"""
        view_name = view.__class__.__name__.lower()

        if 'workflow' in view_name:
            if action in ['create', 'update', 'partial_update', 'destroy']:
                return 'workflows:write'
            elif action == 'execute':
                return 'workflows:execute'
            else:
                return 'workflows:read'

        elif 'node' in view_name:
            if action in ['create', 'update', 'partial_update', 'destroy']:
                return 'nodes:write'
            else:
                return 'nodes:read'

        elif 'analytics' in view_name:
            return 'analytics:read'

        elif 'execution' in view_name:
            return 'executions:read'

        return None


class PlanBasedPermission(BasePermission):
    """
    Permission class that checks organization plan limits
    """

    def has_permission(self, request, view):
        """Check plan-based permissions"""
        if not hasattr(request, 'organization'):
            return False

        organization = request.organization
        action = getattr(view, 'action', None)

        # Check plan-specific limits
        if action == 'create':
            return self._check_creation_limits(organization, view)

        return True

    def _check_creation_limits(self, organization, view):
        """Check if organization can create more resources"""
        view_name = view.__class__.__name__.lower()

        if 'workflow' in view_name:
            current_count = organization.workflows.filter(is_latest_version=True).count()
            return organization.max_workflows == -1 or current_count < organization.max_workflows

        elif 'webhook' in view_name:
            # Example: limit webhooks based on plan
            plan_limits = {
                'free': 5,
                'pro': 50,
                'business': 500,
                'enterprise': -1  # unlimited
            }
            limit = plan_limits.get(organization.plan, 5)
            if limit == -1:
                return True

            current_count = organization.webhook_endpoints.count()
            return current_count < limit

        return True


# Utility functions for permission checking
def check_workflow_permission(user, workflow, permission='view'):
    """Check if user has permission for workflow"""

    # Check organization membership
    try:
        membership = user.organization_memberships.filter(
            organization=workflow.organization,
            status='active'
        ).first()

        if membership:
            if permission == 'view':
                return True
            elif permission == 'edit':
                return membership.role in ['owner', 'admin'] or workflow.created_by == user
            elif permission == 'execute':
                return membership.role in ['owner', 'admin', 'member']
            elif permission == 'admin':
                return membership.role in ['owner', 'admin']

        # Check shared access
        if permission in ['view', 'execute']:
            from apps.workflows.models import WorkflowShare

            try:
                share = WorkflowShare.objects.get(
                    workflow=workflow,
                    shared_with=user
                )

                if permission == 'view':
                    return True
                elif permission == 'execute':
                    return share.permission in ['execute', 'edit', 'admin']

            except WorkflowShare.DoesNotExist:
                pass

        # Check if workflow is public
        if permission == 'view' and workflow.is_public:
            return True

        return False

    except Exception:
        return False


def check_organization_limits(organization, resource_type):
    """Check if organization has reached limits for resource type"""

    if resource_type == 'workflows':
        if organization.max_workflows == -1:
            return True, 0, -1

        current_count = organization.workflows.filter(is_latest_version=True).count()
        return current_count < organization.max_workflows, current_count, organization.max_workflows

    elif resource_type == 'executions':
        from django.utils import timezone
        from datetime import timedelta

        if organization.max_executions_per_month == -1:
            return True, 0, -1

        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_count = organization.workflows.aggregate(
            total_executions=Count('executions', filter=Q(executions__started_at__gte=start_of_month))
        )['total_executions'] or 0

        return current_count < organization.max_executions_per_month, current_count, organization.max_executions_per_month

    return True, 0, -1