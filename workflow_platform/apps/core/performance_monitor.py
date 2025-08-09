"""
Performance Monitoring System for Workflow Platform
"""
import time
import psutil
import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure"""
    timestamp: str
    cpu_usage_percent: float
    memory_usage_mb: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_io_bytes: Dict[str, int]
    active_connections: int
    response_time_ms: float
    throughput_rps: float
    error_rate_percent: float
    cache_hit_rate_percent: float


@dataclass
class ExecutionMetrics:
    """Execution-specific metrics"""
    execution_id: str
    workflow_id: str
    start_time: float
    end_time: Optional[float]
    duration_ms: Optional[float]
    node_count: int
    nodes_executed: int
    nodes_failed: int
    memory_peak_mb: float
    cpu_time_ms: float
    io_operations: int
    cache_operations: int
    database_queries: int


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system
    """

    def __init__(self):
        self.active_executions: Dict[str, ExecutionMetrics] = {}
        self.metrics_history = []
        self.max_history_size = getattr(settings, 'PERFORMANCE_HISTORY_SIZE', 1000)
        self.collection_interval = getattr(settings, 'PERFORMANCE_COLLECTION_INTERVAL', 60)

    async def start_execution_monitoring(self, execution_id: str, workflow_id: str = None, node_count: int = 0):
        """Start monitoring a workflow execution"""
        metrics = ExecutionMetrics(
            execution_id=execution_id,
            workflow_id=workflow_id or '',
            start_time=time.time(),
            end_time=None,
            duration_ms=None,
            node_count=node_count,
            nodes_executed=0,
            nodes_failed=0,
            memory_peak_mb=0,
            cpu_time_ms=0,
            io_operations=0,
            cache_operations=0,
            database_queries=0
        )

        self.active_executions[execution_id] = metrics
        logger.debug(f"Started monitoring execution: {execution_id}")

    async def stop_execution_monitoring(self, execution_id: str):
        """Stop monitoring a workflow execution"""
        if execution_id in self.active_executions:
            metrics = self.active_executions[execution_id]
            metrics.end_time = time.time()
            metrics.duration_ms = (metrics.end_time - metrics.start_time) * 1000

            # Store metrics for analysis
            await self._store_execution_metrics(metrics)

            # Clean up
            del self.active_executions[execution_id]
            logger.debug(f"Stopped monitoring execution: {execution_id}")

    async def update_execution_metrics(self, execution_id: str, **kwargs):
        """Update metrics for an active execution"""
        if execution_id in self.active_executions:
            metrics = self.active_executions[execution_id]
            for key, value in kwargs.items():
                if hasattr(metrics, key):
                    setattr(metrics, key, value)

    async def collect_system_metrics(self) -> PerformanceMetrics:
        """Collect current system performance metrics"""
        try:
            # CPU metrics
            cpu_usage = psutil.cpu_percent(interval=1)

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_usage_mb = memory.used / (1024 * 1024)
            memory_usage_percent = memory.percent

            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_usage_percent = disk.percent

            # Network metrics
            network = psutil.net_io_counters()
            network_io_bytes = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv
            }

            # Active connections
            active_connections = len(psutil.net_connections(kind='tcp'))

            # Application-specific metrics
            response_time_ms = await self._get_average_response_time()
            throughput_rps = await self._get_current_throughput()
            error_rate_percent = await self._get_error_rate()
            cache_hit_rate_percent = await self._get_cache_hit_rate()

            metrics = PerformanceMetrics(
                timestamp=timezone.now().isoformat(),
                cpu_usage_percent=cpu_usage,
                memory_usage_mb=memory_usage_mb,
                memory_usage_percent=memory_usage_percent,
                disk_usage_percent=disk_usage_percent,
                network_io_bytes=network_io_bytes,
                active_connections=active_connections,
                response_time_ms=response_time_ms,
                throughput_rps=throughput_rps,
                error_rate_percent=error_rate_percent,
                cache_hit_rate_percent=cache_hit_rate_percent
            )

            # Store metrics
            await self._store_system_metrics(metrics)

            return metrics

        except Exception as e:
            logger.error(f"Error collecting system metrics: {str(e)}")
            raise

    async def get_performance_summary(self, time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get performance summary for the specified time window"""
        try:
            # Get recent metrics from cache
            cache_key = f"performance_summary_{time_window_minutes}m"
            cached_summary = cache.get(cache_key)

            if cached_summary:
                return cached_summary

            # Calculate summary from stored metrics
            end_time = timezone.now()
            start_time = end_time - timezone.timedelta(minutes=time_window_minutes)

            # Get system metrics
            system_summary = await self._calculate_system_summary(start_time, end_time)

            # Get execution metrics
            execution_summary = await self._calculate_execution_summary(start_time, end_time)

            # Get database metrics
            database_summary = await self._calculate_database_summary(start_time, end_time)

            summary = {
                'time_window_minutes': time_window_minutes,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'system': system_summary,
                'executions': execution_summary,
                'database': database_summary,
                'alerts': await self._check_performance_alerts()
            }

            # Cache summary for 1 minute
            cache.set(cache_key, summary, timeout=60)

            return summary

        except Exception as e:
            logger.error(f"Error generating performance summary: {str(e)}")
            return {}

    async def check_performance_health(self) -> Dict[str, Any]:
        """Check overall system performance health"""
        try:
            current_metrics = await self.collect_system_metrics()

            # Define thresholds
            thresholds = {
                'cpu_critical': 90,
                'cpu_warning': 75,
                'memory_critical': 90,
                'memory_warning': 75,
                'disk_critical': 95,
                'disk_warning': 85,
                'response_time_critical': 5000,  # 5 seconds
                'response_time_warning': 2000,  # 2 seconds
                'error_rate_critical': 10,  # 10%
                'error_rate_warning': 5  # 5%
            }

            health_status = 'healthy'
            issues = []
            recommendations = []

            # Check CPU usage
            if current_metrics.cpu_usage_percent >= thresholds['cpu_critical']:
                health_status = 'critical'
                issues.append(f"Critical CPU usage: {current_metrics.cpu_usage_percent:.1f}%")
                recommendations.append("Scale up worker instances or optimize CPU-intensive tasks")
            elif current_metrics.cpu_usage_percent >= thresholds['cpu_warning']:
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append(f"High CPU usage: {current_metrics.cpu_usage_percent:.1f}%")
                recommendations.append("Monitor CPU usage trends and consider scaling")

            # Check memory usage
            if current_metrics.memory_usage_percent >= thresholds['memory_critical']:
                health_status = 'critical'
                issues.append(f"Critical memory usage: {current_metrics.memory_usage_percent:.1f}%")
                recommendations.append("Increase memory allocation or optimize memory usage")
            elif current_metrics.memory_usage_percent >= thresholds['memory_warning']:
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append(f"High memory usage: {current_metrics.memory_usage_percent:.1f}%")
                recommendations.append("Monitor memory trends and check for memory leaks")

            # Check disk usage
            if current_metrics.disk_usage_percent >= thresholds['disk_critical']:
                health_status = 'critical'
                issues.append(f"Critical disk usage: {current_metrics.disk_usage_percent:.1f}%")
                recommendations.append("Free up disk space or add more storage")
            elif current_metrics.disk_usage_percent >= thresholds['disk_warning']:
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append(f"High disk usage: {current_metrics.disk_usage_percent:.1f}%")
                recommendations.append("Plan for additional storage capacity")

            # Check response time
            if current_metrics.response_time_ms >= thresholds['response_time_critical']:
                health_status = 'critical'
                issues.append(f"Critical response time: {current_metrics.response_time_ms:.0f}ms")
                recommendations.append("Investigate slow queries and optimize performance")
            elif current_metrics.response_time_ms >= thresholds['response_time_warning']:
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append(f"Slow response time: {current_metrics.response_time_ms:.0f}ms")
                recommendations.append("Review application performance and database queries")

            # Check error rate
            if current_metrics.error_rate_percent >= thresholds['error_rate_critical']:
                health_status = 'critical'
                issues.append(f"Critical error rate: {current_metrics.error_rate_percent:.1f}%")
                recommendations.append("Investigate and fix application errors immediately")
            elif current_metrics.error_rate_percent >= thresholds['error_rate_warning']:
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append(f"High error rate: {current_metrics.error_rate_percent:.1f}%")
                recommendations.append("Review error logs and fix common issues")

            return {
                'status': health_status,
                'timestamp': timezone.now().isoformat(),
                'current_metrics': asdict(current_metrics),
                'issues': issues,
                'recommendations': recommendations,
                'active_executions': len(self.active_executions)
            }

        except Exception as e:
            logger.error(f"Error checking performance health: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }

    @asynccontextmanager
    async def monitor_operation(self, operation_name: str):
        """Context manager for monitoring specific operations"""
        start_time = time.time()

        try:
            yield
        finally:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            # Log operation metrics
            logger.debug(f"Operation {operation_name} took {duration_ms:.2f}ms")

            # Store in cache for analytics
            cache_key = f"operation_metrics:{operation_name}"
            metrics = cache.get(cache_key, [])
            metrics.append({
                'timestamp': timezone.now().isoformat(),
                'duration_ms': duration_ms
            })

            # Keep only last 100 measurements
            metrics = metrics[-100:]
            cache.set(cache_key, metrics, timeout=3600)  # 1 hour

    async def _store_execution_metrics(self, metrics: ExecutionMetrics):
        """Store execution metrics for analysis"""
        try:
            # Store in database asynchronously
            from apps.analytics.models import PerformanceSnapshot

            # This would normally be done with a background task
            # For now, we'll store in cache
            cache_key = f"execution_metrics:{metrics.execution_id}"
            cache.set(cache_key, asdict(metrics), timeout=86400)  # 24 hours

        except Exception as e:
            logger.error(f"Error storing execution metrics: {str(e)}")

    async def _store_system_metrics(self, metrics: PerformanceMetrics):
        """Store system metrics for analysis"""
        try:
            # Add to history
            self.metrics_history.append(metrics)

            # Trim history if needed
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history = self.metrics_history[-self.max_history_size:]

            # Store in cache
            cache.set('latest_system_metrics', asdict(metrics), timeout=300)  # 5 minutes

        except Exception as e:
            logger.error(f"Error storing system metrics: {str(e)}")

    async def _get_average_response_time(self) -> float:
        """Get average response time from recent requests"""
        try:
            # This would normally come from application metrics
            # For now, return a simulated value
            cached_times = cache.get('recent_response_times', [])
            if cached_times:
                return sum(cached_times) / len(cached_times)
            return 0.0
        except Exception:
            return 0.0

    async def _get_current_throughput(self) -> float:
        """Get current requests per second"""
        try:
            # This would normally come from application metrics
            # For now, return a simulated value
            return cache.get('current_throughput', 0.0)
        except Exception:
            return 0.0

    async def _get_error_rate(self) -> float:
        """Get current error rate percentage"""
        try:
            # This would normally come from application metrics
            # For now, return a simulated value
            return cache.get('current_error_rate', 0.0)
        except Exception:
            return 0.0

    async def _get_cache_hit_rate(self) -> float:
        """Get cache hit rate percentage"""
        try:
            # This would normally come from Redis/cache metrics
            # For now, return a simulated value
            return cache.get('cache_hit_rate', 0.0)
        except Exception:
            return 0.0

    async def _calculate_system_summary(self, start_time, end_time) -> Dict[str, Any]:
        """Calculate system performance summary"""
        # This would normally query stored metrics
        # For now, return current metrics
        current = await self.collect_system_metrics()
        return {
            'avg_cpu_usage': current.cpu_usage_percent,
            'avg_memory_usage': current.memory_usage_percent,
            'avg_response_time_ms': current.response_time_ms,
            'peak_memory_mb': current.memory_usage_mb,
            'total_requests': 0,  # Would be calculated from stored data
        }

    async def _calculate_execution_summary(self, start_time, end_time) -> Dict[str, Any]:
        """Calculate execution performance summary"""
        # This would normally query execution metrics
        return {
            'total_executions': len(self.active_executions),
            'avg_execution_time_ms': 0,
            'success_rate_percent': 100,
            'active_executions': len(self.active_executions),
        }

    async def _calculate_database_summary(self, start_time, end_time) -> Dict[str, Any]:
        """Calculate database performance summary"""
        # This would normally query database metrics
        return {
            'avg_query_time_ms': 0,
            'total_queries': 0,
            'slow_queries': 0,
            'connection_pool_usage': 0,
        }

    async def _check_performance_alerts(self) -> list:
        """Check for performance alerts"""
        alerts = []

        # Check active executions
        if len(self.active_executions) > 100:
            alerts.append({
                'type': 'high_load',
                'message': f'High number of active executions: {len(self.active_executions)}',
                'severity': 'warning'
            })

        return alerts


# Global performance monitor instance
performance_monitor = PerformanceMonitor()