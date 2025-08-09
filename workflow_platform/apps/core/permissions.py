"""
Core Permissions - Custom permission classes
"""
from rest_framework.permissions import BasePermission
from django.utils import timezone
from django.db.models import Q, Count


class IsAuthenticated(BasePermission):
    """
    Enhanced authentication check with organization context
    """

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return bool(request.user and request.user.is_authenticated)


class OrganizationPermission(BasePermission):
    """
    Permission class for organization-based access control
    """

    def has_permission(self, request, view):
        """Check organization membership"""
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user has active organization membership
        from apps.organizations.models import OrganizationMember

        try:
            membership = OrganizationMember.objects.filter(
                user=request.user,
                status='active'
            ).first()

            if membership:
                request.organization = membership.organization
                request.organization_member = membership
                return True

            return False

        except Exception:
            return False

    def has_object_permission(self, request, view, obj):
        """Check object-level permissions"""
        if not hasattr(request, 'organization'):
            return False

        # Check if object belongs to user's organization
        if hasattr(obj, 'organization'):
            return obj.organization == request.organization

        # For workflow-related objects
        if hasattr(obj, 'workflow') and hasattr(obj.workflow, 'organization'):
            return obj.workflow.organization == request.organization

        return True


class WorkflowPermission(BasePermission):
    """
    Permission class for workflow-specific access control
    """

    def has_permission(self, request, view):
        """Basic workflow access check"""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Check workflow permissions"""
        if not request.user or not request.user.is_authenticated:
            return False

        # Check organization membership
        if hasattr(obj, 'organization') and hasattr(request, 'organization'):
            if obj.organization != request.organization:
                return False

        # Check specific permissions based on action
        action = getattr(view, 'action', None)

        if action in ['retrieve', 'list']:
            return self._has_view_permission(request, obj)
        elif action in ['create', 'update', 'partial_update']:
            return self._has_edit_permission(request, obj)
        elif action == 'destroy':
            return self._has_delete_permission(request, obj)
        elif action == 'execute':
            return self._has_execute_permission(request, obj)

        return True

    def _has_view_permission(self, request, obj):
        """Check view permission"""
        # Organization members can view workflows
        if hasattr(request, 'organization_member'):
            return True

        # Check if workflow is public
        if hasattr(obj, 'is_public') and obj.is_public:
            return True

        # Check if workflow is shared with user
        if hasattr(obj, 'shares'):
            return obj.shares.filter(shared_with=request.user).exists()

        return False

    def _has_edit_permission(self, request, obj):
        """Check edit permission"""
        if not hasattr(request, 'organization_member'):
            return False

        member = request.organization_member

        # Owners and admins can edit any workflow
        if member.role in ['owner', 'admin']:
            return True

        # Members can edit workflows they created
        if hasattr(obj, 'created_by') and obj.created_by == request.user:
            return True

        # Check shared permissions
        if hasattr(obj, 'shares'):
            share = obj.shares.filter(
                shared_with=request.user,
                permission__in=['edit', 'admin']
            ).first()
            return bool(share)

        return False

    def _has_delete_permission(self, request, obj):
        """Check delete permission"""
        if not hasattr(request, 'organization_member'):
            return False

        member = request.organization_member

        # Only owners, admins, and creators can delete
        if member.role in ['owner', 'admin']:
            return True

        if hasattr(obj, 'created_by') and obj.created_by == request.user:
            return True

        return False

    def _has_execute_permission(self, request, obj):
        """Check execute permission"""
        if not hasattr(request, 'organization_member'):
            return False

        # All active members can execute workflows
        return request.organization_member.status == 'active'


class APIKeyPermission(BasePermission):
    """
    Permission class for API key authentication
    """

    def has_permission(self, request, view):
        """Check API key permissions"""
        # Check for API key in headers
        api_key = request.META.get('HTTP_X_API_KEY') or request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')

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

        except:
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

        # Check organization access
        if hasattr(obj, 'organization'):
            return obj.organization == request.organization

        return True

    def _get_required_scope(self, view, action):
        """Get required scope for action"""
        scope_mapping = {
            'list': 'read',
            'retrieve': 'read',
            'create': 'write',
            'update': 'write',
            'partial_update': 'write',
            'destroy': 'delete',
            'execute': 'execute',
        }

        return scope_mapping.get(action, 'read')


class RoleBasedPermission(BasePermission):
    """
    Role-based permission checking
    """

    def __init__(self, required_roles=None, required_permissions=None):
        self.required_roles = required_roles or []
        self.required_permissions = required_permissions or []

    def has_permission(self, request, view):
        """Check role-based permissions"""
        if not hasattr(request, 'organization_member'):
            return False

        member = request.organization_member

        # Check required roles
        if self.required_roles and member.role not in self.required_roles:
            return False

        # Check required permissions
        for permission in self.required_permissions:
            if not member.has_permission(permission):
                return False

        return True


class ResourceLimitPermission(BasePermission):
    """
    Check resource limits for organization
    """

    def has_permission(self, request, view):
        """Check if organization has not exceeded resource limits"""
        if not hasattr(request, 'organization'):
            return True  # Skip check if no organization context

        organization = request.organization
        action = getattr(view, 'action', None)

        # Check workflow creation limits
        if action == 'create' and hasattr(view, 'get_queryset'):
            model = getattr(view, 'queryset', None)
            if model and hasattr(model, 'model'):
                model_name = model.model.__name__.lower()

                if model_name == 'workflow':
                    return self._check_workflow_limit(organization)
                elif model_name == 'executionqueue':
                    return self._check_execution_limit(organization)

        return True

    def _check_workflow_limit(self, organization):
        """Check workflow creation limits"""
        if organization.max_workflows == -1:  # Unlimited
            return True

        current_count = organization.workflows.filter(is_latest_version=True).count()
        return current_count < organization.max_workflows

    def _check_execution_limit(self, organization):
        """Check execution limits"""
        if organization.max_executions_per_month == -1:  # Unlimited
            return True

        # Check current month executions
        from datetime import datetime
        start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        current_count = organization.workflows.aggregate(
            total_executions=Count(
                'executions',
                filter=Q(executions__started_at__gte=start_of_month)
            )
        )['total_executions'] or 0

        return current_count < organization.max_executions_per_month


# Helper functions for permission checking

def check_workflow_permission(user, workflow, permission='view'):
    """Check if user has permission for workflow"""

    # Check organization membership
    try:
        from apps.organizations.models import OrganizationMember

        membership = OrganizationMember.objects.filter(
            user=user,
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
        if organization.max_executions_per_month == -1:
            return True, 0, -1

        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_count = organization.workflows.aggregate(
            total_executions=Count('executions', filter=Q(executions__started_at__gte=start_of_month))
        )['total_executions'] or 0

        return current_count < organization.max_executions_per_month, current_count, organization.max_executions_per_month

    return True, 0, -1


# Permission decorators

def organization_required(view_func):
    """Decorator to ensure organization context"""
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'organization') or not request.organization:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'Organization context required'},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(roles):
    """Decorator to check required roles"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not hasattr(request, 'organization_member'):
                from django.http import JsonResponse
                return JsonResponse(
                    {'error': 'Organization membership required'},
                    status=403
                )

            if request.organization_member.role not in roles:
                from django.http import JsonResponse
                return JsonResponse(
                    {'error': 'Insufficient permissions'},
                    status=403
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator