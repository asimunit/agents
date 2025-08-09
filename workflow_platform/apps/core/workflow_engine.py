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
            max_workers=settings.MAX_PARALLEL_EXECUTIONS
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
            logger.error(f"Workflow execution failed: {str(e)}", exc_info=True)
            execution.mark_failed(str(e), {'traceback': traceback.format_exc()})
            raise

        finally:
            # Stop performance monitoring
            await self.performance_monitor.stop_execution_monitoring(execution.id)

            # Cleanup
            if str(execution.id) in self.active_executions:
                del self.active_executions[str(execution.id)]

        return execution

    async def _execute_workflow_async(
            self,
            workflow: Workflow,
            context: ExecutionContext,
            execution: WorkflowExecution
    ):
        """Execute workflow nodes with parallel processing"""

        # Build execution graph
        execution_graph = self._build_execution_graph(workflow.nodes, workflow.connections)

        # Get execution order with parallel groups
        execution_plan = self._create_execution_plan(execution_graph)

        logger.info(f"Executing workflow with {len(execution_plan)} stages")

        # Execute each stage
        for stage_index, node_group in enumerate(execution_plan):
            logger.debug(f"Executing stage {stage_index + 1}: {[n['id'] for n in node_group]}")

            # Execute nodes in parallel within the stage
            if len(node_group) == 1:
                # Single node - execute directly
                await self._execute_node(node_group[0], context, execution)
            else:
                # Multiple nodes - execute in parallel
                await self._execute_nodes_parallel(node_group, context, execution)

            # Check for execution timeout
            elapsed = (timezone.now() - context.start_time).total_seconds()
            if elapsed > workflow.execution_timeout:
                raise WorkflowTimeoutError(f"Workflow exceeded timeout of {workflow.execution_timeout}s")

    def _build_execution_graph(self, nodes: List[Dict], connections: List[Dict]) -> Dict[str, Dict]:
        """Build a graph representation of the workflow"""
        graph = {}

        # Initialize nodes
        for node in nodes:
            graph[node['id']] = {
                'node': node,
                'dependencies': [],
                'dependents': [],
                'executed': False
            }

        # Add connections
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
        node_name = node.get('name', node_id)
        node_type_name = node['type']

        # Create node execution log
        log_entry = await self._create_node_log(execution, node, node_type_name)

        try:
            logger.debug(f"Executing node: {node_name} ({node_type_name})")

            # Get node type configuration
            node_type = await self._get_node_type(node_type_name)

            # Prepare input data
            input_data = await self._prepare_node_input(node, context)

            # Execute node with timeout
            start_time = time.time()

            output_data = await asyncio.wait_for(
                self.node_executor.execute_node(node_type, node.get('configuration', {}), input_data, context),
                timeout=node.get('timeout', node_type.default_timeout)
            )

            execution_time = (time.time() - start_time) * 1000  # milliseconds

            # Store output in context
            self._store_node_output(node_id, output_data, context)

            # Update log entry
            log_entry.mark_completed(output_data)
            log_entry.execution_time = execution_time
            log_entry.save()

            # Update execution statistics
            execution.nodes_executed += 1
            execution.save(update_fields=['nodes_executed'])

            logger.debug(f"Node {node_name} completed in {execution_time:.2f}ms")

        except asyncio.TimeoutError:
            error_msg = f"Node {node_name} timed out"
            logger.error(error_msg)

            log_entry.mark_failed(error_msg, 'TimeoutError')
            execution.nodes_failed += 1
            execution.save(update_fields=['nodes_failed'])

            # Check if node supports retry
            if await self._should_retry_node(node, log_entry):
                await self._retry_node(node, context, execution, log_entry)
            else:
                raise NodeExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Node {node_name} failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            log_entry.mark_failed(
                error_msg,
                type(e).__name__,
                {'error': str(e)},
                traceback.format_exc()
            )
            execution.nodes_failed += 1
            execution.save(update_fields=['nodes_failed'])

            # Check if node supports retry
            if await self._should_retry_node(node, log_entry):
                await self._retry_node(node, context, execution, log_entry)
            else:
                raise NodeExecutionError(error_msg) from e

    async def _should_retry_node(self, node: Dict, log_entry: NodeExecutionLog) -> bool:
        """Determine if a node should be retried"""
        node_config = node.get('configuration', {})
        max_retries = node_config.get('maxRetries', 3)

        # Check if retries are enabled and we haven't exceeded the limit
        return (
                node_config.get('enableRetry', True) and
                log_entry.retry_count < max_retries and
                log_entry.error_type not in ['ValidationError', 'ConfigurationError']
        )

    async def _retry_node(
            self,
            node: Dict,
            context: ExecutionContext,
            execution: WorkflowExecution,
            original_log: NodeExecutionLog
    ):
        """Retry node execution with exponential backoff"""
        retry_delay = node.get('configuration', {}).get('retryDelay', 60)
        retry_count = original_log.retry_count + 1

        # Exponential backoff
        delay = retry_delay * (2 ** (retry_count - 1))

        logger.info(f"Retrying node {node.get('name')} in {delay} seconds (attempt {retry_count})")

        await asyncio.sleep(delay)

        # Create new log entry for retry
        log_entry = await self._create_node_log(execution, node, node['type'])
        log_entry.retry_count = retry_count
        log_entry.is_retry = True
        log_entry.save()

        # Retry execution
        await self._execute_node(node, context, execution)

    async def _prepare_node_input(self, node: Dict, context: ExecutionContext) -> Dict[str, Any]:
        """Prepare input data for node execution"""
        input_data = {}

        # Get input mappings from node configuration
        input_mappings = node.get('inputMappings', {})

        for input_name, mapping in input_mappings.items():
            if isinstance(mapping, str):
                # Simple reference to another node's output
                if '.' in mapping:
                    node_ref, output_name = mapping.split('.', 1)
                    input_data[input_name] = context.get_node_output(node_ref, output_name)
                else:
                    # Reference to workflow variable
                    input_data[input_name] = context.get_variable(mapping)
            elif isinstance(mapping, dict):
                # Complex mapping with transformations
                input_data[input_name] = await self._process_input_mapping(mapping, context)

        return input_data

    async def _process_input_mapping(self, mapping: Dict, context: ExecutionContext) -> Any:
        """Process complex input mappings with transformations"""
        if 'source' in mapping:
            source = mapping['source']
            if '.' in source:
                node_ref, output_name = source.split('.', 1)
                value = context.get_node_output(node_ref, output_name)
            else:
                value = context.get_variable(source)

            # Apply transformations
            transformations = mapping.get('transformations', [])
            for transform in transformations:
                value = await self._apply_transformation(value, transform)

            return value

        return mapping.get('default')

    async def _apply_transformation(self, value: Any, transform: Dict) -> Any:
        """Apply data transformation"""
        transform_type = transform.get('type')

        if transform_type == 'json_path':
            # JSONPath extraction
            import jsonpath_ng
            expr = jsonpath_ng.parse(transform['expression'])
            matches = [match.value for match in expr.find(value)]
            return matches[0] if matches else None

        elif transform_type == 'string_format':
            # String formatting
            return transform['template'].format(value=value)

        elif transform_type == 'date_format':
            # Date formatting
            from datetime import datetime
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            return value.strftime(transform['format'])

        # Add more transformation types as needed
        return value

    def _store_node_output(self, node_id: str, output_data: Dict[str, Any], context: ExecutionContext):
        """Store node output in execution context"""
        for output_name, value in output_data.items():
            context.set_node_output(node_id, output_name, value)

    async def _create_execution_record(
            self,
            workflow: Workflow,
            input_data: Dict[str, Any],
            triggered_by_user_id: Optional[str],
            trigger_source: str
    ) -> WorkflowExecution:
        """Create workflow execution record"""

        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            trigger_source=trigger_source,
            triggered_by_id=triggered_by_user_id,
            input_data=input_data or {},
            status='running'
        )

        # Track active execution
        self.active_executions[str(execution.id)] = None

        return execution

    async def _create_node_log(
            self,
            execution: WorkflowExecution,
            node: Dict,
            node_type_name: str
    ) -> NodeExecutionLog:
        """Create node execution log entry"""

        try:
            node_type = await self._get_node_type(node_type_name)
        except NodeType.DoesNotExist:
            # Create a placeholder for unknown node types
            node_type = None

        log_entry = NodeExecutionLog.objects.create(
            execution=execution,
            node_id=node['id'],
            node_type=node_type,
            node_name=node.get('name', node['id']),
            status='running',
            input_data={}
        )

        return log_entry

    async def _get_node_type(self, node_type_name: str) -> NodeType:
        """Get node type by name with caching"""
        cache_key = f"node_type_{node_type_name}"

        if cache_key in self._execution_cache:
            return self._execution_cache[cache_key]

        try:
            node_type = await NodeType.objects.aget(name=node_type_name, is_active=True)
            self._execution_cache[cache_key] = node_type
            return node_type
        except NodeType.DoesNotExist:
            raise NodeExecutionError(f"Node type '{node_type_name}' not found or inactive")

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running workflow execution"""

        if execution_id in self.active_executions:
            task = self.active_executions[execution_id]
            if task and not task.done():
                task.cancel()

                # Update execution record
                try:
                    execution = await WorkflowExecution.objects.aget(id=execution_id)
                    execution.status = 'cancelled'
                    execution.completed_at = timezone.now()
                    await execution.asave()
                except WorkflowExecution.DoesNotExist:
                    pass

                logger.info(f"Cancelled execution: {execution_id}")
                return True

        return False

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get current execution status"""

        if execution_id in self.active_executions:
            task = self.active_executions[execution_id]
            if task:
                return {
                    'status': 'running',
                    'is_done': task.done(),
                    'is_cancelled': task.cancelled(),
                }

        return {'status': 'unknown'}

    async def cleanup_old_executions(self, days: int = 30):
        """Cleanup old execution records and logs"""

        cutoff_date = timezone.now() - timedelta(days=days)

        # Delete old execution logs
        deleted_logs = await NodeExecutionLog.objects.filter(
            started_at__lt=cutoff_date
        ).adelete()

        # Delete old executions
        deleted_executions = await WorkflowExecution.objects.filter(
            started_at__lt=cutoff_date
        ).adelete()

        logger.info(f"Cleaned up {deleted_executions[0]} executions and {deleted_logs[0]} logs")

        return deleted_executions[0], deleted_logs[0]


# Global workflow engine instance
workflow_engine = WorkflowEngine()