"""
Core Pagination - Custom pagination classes
"""
from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination
from rest_framework.response import Response
from collections import OrderedDict


class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom page number pagination with enhanced metadata
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return paginated response with enhanced metadata"""
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.page.has_next()),
            ('has_previous', self.page.has_previous()),
            ('start_index', self.page.start_index()),
            ('end_index', self.page.end_index()),
            ('results', data)
        ]))


class CustomLimitOffsetPagination(LimitOffsetPagination):
    """
    Custom limit/offset pagination with enhanced metadata
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_paginated_response(self, data):
        """Return paginated response with enhanced metadata"""
        total_count = self.count
        current_offset = self.offset
        current_limit = self.limit

        return Response(OrderedDict([
            ('count', total_count),
            ('limit', current_limit),
            ('offset', current_offset),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.get_next_link() is not None),
            ('has_previous', self.get_previous_link() is not None),
            ('start_index', current_offset + 1 if total_count > 0 else 0),
            ('end_index', min(current_offset + current_limit, total_count)),
            ('results', data)
        ]))


class SmallResultsPagination(PageNumberPagination):
    """
    Pagination for small result sets (dashboard widgets, etc.)
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class LargeResultsPagination(PageNumberPagination):
    """
    Pagination for large result sets (logs, analytics, etc.)
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class ExecutionLogsPagination(PageNumberPagination):
    """
    Specialized pagination for execution logs with performance optimization
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return paginated response with execution-specific metadata"""
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.page.has_next()),
            ('has_previous', self.page.has_previous()),
            ('start_index', self.page.start_index()),
            ('end_index', self.page.end_index()),
            ('results', data),
            ('metadata', {
                'total_executions': self.page.paginator.count,
                'page_info': f"Showing {self.page.start_index()}-{self.page.end_index()} of {self.page.paginator.count} executions"
            })
        ]))


class AnalyticsPagination(PageNumberPagination):
    """
    Specialized pagination for analytics data
    """
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        """Return paginated response with analytics metadata"""
        # Calculate some basic statistics if applicable
        stats = {}
        if data and isinstance(data, list) and len(data) > 0:
            # Try to calculate basic stats for numeric fields
            try:
                if isinstance(data[0], dict):
                    numeric_fields = []
                    for key, value in data[0].items():
                        if isinstance(value, (int, float)):
                            numeric_fields.append(key)

                    for field in numeric_fields:
                        values = [item.get(field, 0) for item in data if isinstance(item.get(field), (int, float))]
                        if values:
                            stats[f'{field}_sum'] = sum(values)
                            stats[f'{field}_avg'] = sum(values) / len(values)
                            stats[f'{field}_min'] = min(values)
                            stats[f'{field}_max'] = max(values)
            except Exception:
                pass  # Ignore stats calculation errors

        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.page.has_next()),
            ('has_previous', self.page.has_previous()),
            ('start_index', self.page.start_index()),
            ('end_index', self.page.end_index()),
            ('results', data),
            ('page_stats', stats) if stats else None
        ]))


class CursorPaginationForStreaming(PageNumberPagination):
    """
    Cursor-based pagination for real-time streaming data
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return paginated response with cursor information"""
        # Get cursor information for real-time updates
        cursor_info = {}
        if data and isinstance(data, list) and len(data) > 0:
            try:
                # Use the first item's timestamp or ID as cursor
                first_item = data[0]
                last_item = data[-1]

                if isinstance(first_item, dict):
                    # Try to find timestamp or ID fields
                    for field in ['created_at', 'updated_at', 'timestamp', 'id']:
                        if field in first_item:
                            cursor_info['first_cursor'] = str(first_item[field])
                            cursor_info['last_cursor'] = str(last_item[field])
                            break
            except Exception:
                pass

        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.page.has_next()),
            ('has_previous', self.page.has_previous()),
            ('start_index', self.page.start_index()),
            ('end_index', self.page.end_index()),
            ('cursor_info', cursor_info),
            ('results', data)
        ]))


# Utility functions for pagination

def get_pagination_class_for_model(model_name):
    """
    Get appropriate pagination class based on model type
    """
    pagination_mapping = {
        'workflowexecution': ExecutionLogsPagination,
        'nodeexecutionlog': ExecutionLogsPagination,
        'webhookdelivery': LargeResultsPagination,
        'analyticsmetric': AnalyticsPagination,
        'usageanalytics': AnalyticsPagination,
        'performancemetrics': AnalyticsPagination,
        'executionhistory': LargeResultsPagination,
        'executionqueue': CustomPageNumberPagination,
        'workflow': CustomPageNumberPagination,
        'dashboard': SmallResultsPagination,
        'widget': SmallResultsPagination,
    }

    return pagination_mapping.get(model_name.lower(), CustomPageNumberPagination)


def paginate_queryset(queryset, request, pagination_class=None):
    """
    Helper function to paginate any queryset
    """
    if pagination_class is None:
        pagination_class = CustomPageNumberPagination

    paginator = pagination_class()
    page = paginator.paginate_queryset(queryset, request)

    if page is not None:
        return page, paginator

    return queryset, None


class NoPagination:
    """
    Disable pagination for specific views
    """
    def paginate_queryset(self, queryset, request, view=None):
        return None

    def get_paginated_response(self, data):
        return Response(data)