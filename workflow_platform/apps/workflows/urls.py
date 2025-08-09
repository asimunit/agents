"""
Workflows URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkflowViewSet,
    WorkflowExecutionViewSet,
    WorkflowTemplateViewSet,
    WorkflowCommentViewSet,
    WorkflowShareViewSet,
    WorkflowCategoryViewSet,
    workflow_stats,
    export_workflow,
    import_workflow,
    workflow_analytics,
    clone_workflow
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'', WorkflowViewSet, basename='workflows')
router.register(r'executions', WorkflowExecutionViewSet, basename='workflow-executions')
router.register(r'templates', WorkflowTemplateViewSet, basename='workflow-templates')
router.register(r'comments', WorkflowCommentViewSet, basename='workflow-comments')
router.register(r'shares', WorkflowShareViewSet, basename='workflow-shares')
router.register(r'categories', WorkflowCategoryViewSet, basename='workflow-categories')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Custom workflow endpoints
    path('stats/', workflow_stats, name='workflow_stats'),
    path('<uuid:workflow_id>/export/', export_workflow, name='export_workflow'),
    path('<uuid:workflow_id>/clone/', clone_workflow, name='clone_workflow'),
    path('<uuid:workflow_id>/analytics/', workflow_analytics, name='workflow_analytics'),
    path('import/', import_workflow, name='import_workflow'),
]

app_name = 'workflows'