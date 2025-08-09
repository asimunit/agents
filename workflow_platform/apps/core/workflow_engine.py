"""
Advanced Workflow Engine - Core execution engine that outperforms N8n
"""
import asyncio
import logging
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.db import transaction

from apps.workflows.models import Workflow, WorkflowExecution
from apps.nodes.models import NodeType, NodeExecutionLog
from apps.core.node_executor import NodeExecutor
from apps.core.performance_monitor import PerformanceMonitor
from apps.core.exceptions import (
    WorkflowExecutionError,
    NodeExecutionError,
    WorkflowTimeoutError,
    WorkflowValidationError
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Execution context for workflow runs"""
    workflow_id: str
    execution_id: str
    organization_id: str
    user_id: Optional[str]
    input_data: Dict[str, Any]
    variables: Dict[str, Any]
    node_outputs: Dict[str, Any]
    metadata: Dict[str, Any]
    start_time: datetime

    def get_variable(self, name: str, default=None):
        """Get workflow variable with default"""
        return self.variables.get(name, default)

    def set_variable(self, name: str, value: Any):
        """Set workflow variable"""
        self.variables[name] = value

    def get_node_output(self, node_id: str, output_name: str = 'main', default=None):
        """Get output from a specific node"""
        return self.node_outputs.get(f"{node_id}.{output_name}", default)

    def set_node_output(self, node_id: str, output_name: str, value: Any):
        """Set output for a specific node"""
        self.node_outputs[f"{node_id}.{output_name}"] = value


class WorkflowEngine:
    """
    Advanced workflow execution engine with parallel processing,
    error recovery, and performance optimization
    """

    def __init__(self):
        self.executor_pool = ThreadPoolExecutor(
            max_workers=getattr(settings, 'MAX_PARALLEL_EXECUTIONS', 10)
        )
        self.performance_monitor = PerformanceMonitor()
        self.node_executor = NodeExecutor()

        # Execution tracking
        self.active_executions: Dict[str, asyncio.Task] = {}

        # Performance cache
        self._execution_cache = {}

    async def execute_workflow(
            self,
            workflow: Workflow,
            input_data: Dict[str, Any] = None,
            triggered_by_user_id: Optional[str] = None,
            trigger_source: str = 'manual'
    ) -> WorkflowExecution:
        """
        Execute a workflow with advanced error handling and monitoring
        """
        execution = await self._create_execution_record(
            workflow, input_data, triggered_by_user_id, trigger_source
        )

        try:
            # Validate workflow before execution
            validation_errors = workflow.validate_workflow()
            if validation_errors:
                raise WorkflowValidationError(f"Workflow validation failed: {validation_errors}")

            # Create execution context
            context = ExecutionContext(
                workflow_id=str(workflow.id),
                execution_id=str(execution.id),
                organization_id=str(workflow.organization.id),
                user_id=triggered_by_user_id,
                input_data=input_data or {},
                variables=workflow.variables.copy(),
                node_outputs={},
                metadata={},
                start_time=timezone.now()
            )

            # Start performance monitoring
            await self.performance_monitor.start_execution_monitoring(execution.id)

            # Execute workflow
            await self._execute_workflow_async(workflow, context, execution)

            # Mark as completed
            execution.mark_completed(context.node_outputs)

            logger.info(f"Workflow {workflow.name} executed successfully: {execution.id}")

        except Exception as e:
            logger.error(f"Workflow execution failed: {str(e)}")
            execution.mark_failed(str(e), traceback.format_exc())
            raise

        finally:
            # Clean up active execution tracking
            self.active_executions.pop(str(execution.id), None)
            # Stop performance monitoring
            await self.performance_monitor.stop_execution_monitoring(execution.id)

        return execution

    async def _create_execution_record(
            self,
            workflow: Workflow,
            input_data: Dict[str, Any],
            triggered_by_user_id: Optional[str],
            trigger_source: str
    ) -> WorkflowExecution:
        """Create execution record in database"""
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            triggered_by_user_id=triggered_by_user_id,
            trigger_source=trigger_source,
            input_data=input_data or {},
            status='running'
        )
        return execution

    async def _execute_workflow_async(
            self,
            workflow: Workflow,
            context: ExecutionContext,
            execution: WorkflowExecution
    ):
        """Execute workflow asynchronously with parallel node execution"""

        # Build execution graph
        execution_graph = self._build_execution_graph(workflow.workflow_data)

        # Create execution plan with parallel stages
        execution_plan = self._create_execution_plan(execution_graph)

        logger.info(f"Executing workflow {workflow.name} with {len(execution_plan)} stages")

        # Execute each stage
        for stage_index, stage_nodes in enumerate(execution_plan):
            logger.debug(f"Executing stage {stage_index + 1} with {len(stage_nodes)} nodes")

            # Execute nodes in parallel within this stage
            await self._execute_nodes_parallel(stage_nodes, context, execution)

            logger.debug(f"Stage {stage_index + 1} completed successfully")

    def _build_execution_graph(self, workflow_data: Dict[str, Any]) -> Dict[str, Dict]:
        """Build execution graph from workflow data"""
        nodes = workflow_data.get('nodes', [])
        connections = workflow_data.get('connections', [])

        # Initialize graph
        graph = {}
        for node in nodes:
            graph[node['id']] = {
                'node': node,
                'dependencies': [],
                'dependents': [],
                'executed': False
            }

        # Build dependencies from connections
        for connection in connections:
            source_id = connection['source']
            target_id = connection['target']

            if source_id in graph and target_id in graph:
                graph[target_id]['dependencies'].append(source_id)
                graph[source_id]['dependents'].append(target_id)

        return graph

    def _create_execution_plan(self, graph: Dict[str, Dict]) -> List[List[Dict]]:
        """Create execution plan with parallel stages"""
        execution_plan = []
        remaining_nodes = set(graph.keys())

        while remaining_nodes:
            # Find nodes with no unexecuted dependencies
            ready_nodes = []
            for node_id in remaining_nodes:
                dependencies = graph[node_id]['dependencies']
                unexecuted_deps = [dep for dep in dependencies if not graph[dep]['executed']]

                if not unexecuted_deps:
                    ready_nodes.append(graph[node_id]['node'])
                    graph[node_id]['executed'] = True

            if not ready_nodes:
                raise WorkflowExecutionError("Circular dependency detected in workflow")

            execution_plan.append(ready_nodes)

            # Remove executed nodes
            for node in ready_nodes:
                remaining_nodes.remove(node['id'])

        return execution_plan

    async def _execute_nodes_parallel(
            self,
            nodes: List[Dict],
            context: ExecutionContext,
            execution: WorkflowExecution
    ):
        """Execute multiple nodes in parallel"""
        tasks = []

        for node in nodes:
            task = asyncio.create_task(
                self._execute_node(node, context, execution)
            )
            tasks.append(task)

        # Wait for all nodes to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                node_name = nodes[i].get('name', nodes[i]['id'])
                logger.error(f"Node {node_name} failed: {str(result)}")
                raise result

    async def _execute_node(
            self,
            node: Dict,
            context: ExecutionContext,
            execution: WorkflowExecution
    ):
        """Execute a single node with comprehensive logging and error handling"""
        node_id = node['id']
        node_type_name = node['type']
        node_name = node.get('name', node_id)

        start_time = time.time()

        # Create node execution log
        node_log = NodeExecutionLog.objects.create(
            execution=execution,
            node_id=node_id,
            node_name=node_name,
            node_type_name=node_type_name,
            status='running',
            started_at=timezone.now()
        )

        try:
            # Get node type
            node_type = NodeType.objects.get(name=node_type_name, is_active=True)

            # Prepare input data for this node
            input_data = self._prepare_node_input(node, context)

            # Get node configuration
            configuration = node.get('configuration', {})

            # Execute node
            result = await self.node_executor.execute_node(
                node_type=node_type,
                configuration=configuration,
                input_data=input_data,
                context=context
            )

            # Store node output in context
            context.set_node_output(node_id, 'main', result)

            # Update execution log
            execution_time = (time.time() - start_time) * 1000  # milliseconds
            node_log.mark_completed(result, execution_time)

            logger.debug(f"Node {node_name} executed successfully in {execution_time:.2f}ms")

            return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_details = {
                'error': str(e),
                'traceback': traceback.format_exc(),
                'node_id': node_id,
                'node_type': node_type_name
            }

            # Update execution log with error
            node_log.mark_failed(str(e), error_details)

            logger.error(f"Node {node_name} execution failed: {str(e)}")
            raise NodeExecutionError(f"Node {node_name} execution failed: {str(e)}") from e

    def _prepare_node_input(self, node: Dict, context: ExecutionContext) -> Dict[str, Any]:
        """Prepare input data for node execution"""
        node_id = node['id']

        # Start with workflow input data
        input_data = context.input_data.copy()

        # Add outputs from previous nodes based on connections
        # This would need to be enhanced based on your specific connection logic

        # Add any node-specific input configuration
        if 'input' in node:
            input_data.update(node['input'])

        return input_data

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running workflow execution"""
        if execution_id in self.active_executions:
            task = self.active_executions[execution_id]
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Workflow execution {execution_id} cancelled successfully")

                # Update execution record
                try:
                    execution = WorkflowExecution.objects.get(id=execution_id)
                    execution.mark_cancelled()
                except WorkflowExecution.DoesNotExist:
                    pass

                return True

        return False

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get current status of workflow execution"""
        try:
            execution = WorkflowExecution.objects.get(id=execution_id)

            status_info = {
                'id': str(execution.id),
                'status': execution.status,
                'started_at': execution.started_at,
                'completed_at': execution.completed_at,
                'progress': self._calculate_execution_progress(execution),
                'is_active': execution_id in self.active_executions
            }

            if execution.status == 'failed':
                status_info['error'] = execution.error_message

            return status_info

        except WorkflowExecution.DoesNotExist:
            return {'error': 'Execution not found'}

    def _calculate_execution_progress(self, execution: WorkflowExecution) -> Dict[str, Any]:
        """Calculate execution progress based on node logs"""
        node_logs = NodeExecutionLog.objects.filter(execution=execution)

        total_nodes = node_logs.count()
        completed_nodes = node_logs.filter(status__in=['completed', 'failed']).count()

        if total_nodes == 0:
            return {'percentage': 0, 'nodes_completed': 0, 'total_nodes': 0}

        percentage = (completed_nodes / total_nodes) * 100

        return {
            'percentage': round(percentage, 2),
            'nodes_completed': completed_nodes,
            'total_nodes': total_nodes
        }

    async def cleanup_old_executions(self, days_old: int = 30):
        """Clean up old execution records"""
        cutoff_date = timezone.now() - timedelta(days=days_old)

        old_executions = WorkflowExecution.objects.filter(
            started_at__lt=cutoff_date,
            status__in=['completed', 'failed', 'cancelled']
        )

        count = old_executions.count()
        old_executions.delete()

        logger.info(f"Cleaned up {count} old workflow executions")

        return count