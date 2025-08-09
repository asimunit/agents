"""
Core Signals - Global signal handlers
"""
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def handle_user_creation(sender, instance, created, **kwargs):
    """Handle user creation events"""
    if created:
        try:
            # Create user profile if it doesn't exist
            from apps.authentication.models import UserProfile

            if not hasattr(instance, 'profile'):
                UserProfile.objects.create(user=instance)

            logger.info(f"User created: {instance.username} ({instance.email})")

        except Exception as e:
            logger.error(f"Error handling user creation: {str(e)}")


@receiver(post_save)
def handle_model_updates(sender, instance, created, **kwargs):
    """Handle general model update events for analytics"""
    try:
        # Skip if not from our apps
        if not sender._meta.app_label.startswith('apps.'):
            return

        # Update usage analytics for certain models
        model_name = sender.__name__.lower()

        if model_name in ['workflow', 'workflowexecution', 'organizationmember']:
            from apps.analytics.tasks import update_usage_analytics

            # Get organization from instance
            organization = getattr(instance, 'organization', None)
            if not organization and hasattr(instance, 'workflow'):
                organization = getattr(instance.workflow, 'organization', None)

            if organization:
                # Queue task to update analytics (would use Celery in production)
                try:
                    update_usage_analytics.delay(organization.id)
                except AttributeError:
                    # Fallback if Celery is not configured
                    pass

    except Exception as e:
        logger.error(f"Error in model update handler: {str(e)}")


@receiver(pre_delete)
def handle_model_deletion(sender, instance, **kwargs):
    """Handle model deletion events"""
    try:
        model_name = sender.__name__.lower()

        # Log important deletions
        if model_name in ['organization', 'workflow', 'user']:
            logger.warning(f"Deleting {model_name}: {instance}")

        # Handle workflow deletion
        if model_name == 'workflow':
            # Cancel any running executions
            try:
                from apps.executions.models import ExecutionQueue

                ExecutionQueue.objects.filter(
                    workflow=instance,
                    status__in=['pending', 'running']
                ).update(status='cancelled')

            except Exception as e:
                logger.error(f"Error cancelling executions: {str(e)}")

        # Handle organization deletion
        elif model_name == 'organization':
            # Clean up related data
            try:
                # Delete API keys
                instance.api_keys.all().delete()

                # Delete usage data
                instance.usage_analytics.all().delete()

            except Exception as e:
                logger.error(f"Error cleaning up organization data: {str(e)}")

    except Exception as e:
        logger.error(f"Error in deletion handler: {str(e)}")


@receiver(post_delete)
def handle_post_deletion(sender, instance, **kwargs):
    """Handle post-deletion cleanup"""
    try:
        model_name = sender.__name__.lower()

        # Update analytics after deletions
        if model_name in ['workflow', 'organizationmember']:
            # Update organization usage statistics
            organization = getattr(instance, 'organization', None)
            if organization:
                from apps.analytics.tasks import update_usage_analytics

                try:
                    update_usage_analytics.delay(organization.id)
                except AttributeError:
                    pass

    except Exception as e:
        logger.error(f"Error in post-deletion handler: {str(e)}")