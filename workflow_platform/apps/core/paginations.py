"""
Custom Pagination Classes for Workflow Platform
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
    page_query_param = 'page'

    def get_paginated_response(self, data):
        """
        Enhanced pagination response with additional metadata
        """
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('has_next', self.page.has_next()),
            ('has_previous', self.page.has_previous()),
            ('results', data)
        ]))

    def get_page_size(self, request):
        """Get the page size for this request"""
        if self.page_size_query_param:
            try:
                return int(request.query_params[self.page_size_query_param])
            except (KeyError, ValueError):
                pass
        return self.page_size


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for large result sets with smaller default page size
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for small result sets with larger default page size
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class CustomLimitOffsetPagination(LimitOffsetPagination):
    """
    Custom limit/offset pagination for API clients that prefer offset-based pagination
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_paginated_response(self, data):
        """
        Enhanced limit/offset pagination response
        """
        return Response(OrderedDict([
            ('count', self.count),
            ('limit', self.get_limit(self.request)),
            ('offset', self.get_offset(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class AnalyticsPagination(PageNumberPagination):
    """
    Specialized pagination for analytics data
    """
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

    def get_paginated_response(self, data):
        """
        Analytics-specific pagination response with aggregation metadata
        """
        response_data = OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ])

        # Add aggregation metadata if available
        if hasattr(self, 'aggregation_data'):
            response_data['aggregations'] = self.aggregation_data

        return Response(response_data)


class ExecutionLogsPagination(PageNumberPagination):
    """
    Specialized pagination for execution logs with performance optimization
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """
        Execution logs pagination with performance metadata
        """
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('performance', {
                'query_time_ms': getattr(self, 'query_time_ms', None),
                'cache_hit': getattr(self, 'cache_hit', False),
            }),
            ('results', data)
        ]))


class CursorPagination(PageNumberPagination):
    """
    Cursor-based pagination for real-time data streams
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    cursor_query_param = 'cursor'
    ordering = '-created_at'  # Default ordering

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset using cursor-based pagination
        """
        self.request = request
        cursor = request.query_params.get(self.cursor_query_param)

        if cursor:
            # Decode cursor and filter queryset
            try:
                import base64
                import json
                decoded_cursor = json.loads(base64.b64decode(cursor).decode())
                cursor_value = decoded_cursor.get('value')
                cursor_field = decoded_cursor.get('field', 'created_at')

                if self.ordering.startswith('-'):
                    # Descending order
                    filter_kwargs = {f"{cursor_field}__lt": cursor_value}
                else:
                    # Ascending order
                    filter_kwargs = {f"{cursor_field}__gt": cursor_value}

                queryset = queryset.filter(**filter_kwargs)
            except Exception:
                # Invalid cursor, ignore
                pass

        # Apply ordering
        if self.ordering:
            queryset = queryset.order_by(self.ordering)

        # Get page size
        page_size = self.get_page_size(request)

        # Get one extra item to check if there's a next page
        items = list(queryset[:page_size + 1])

        has_next = len(items) > page_size
        if has_next:
            items = items[:-1]

        # Generate next cursor
        next_cursor = None
        if has_next and items:
            cursor_field = self.ordering.lstrip('-')
            cursor_value = getattr(items[-1], cursor_field)

            import base64
            import json
            cursor_data = {
                'field': cursor_field,
                'value': cursor_value.isoformat() if hasattr(cursor_value, 'isoformat') else str(cursor_value)
            }
            next_cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()

        self.has_next = has_next
        self.next_cursor = next_cursor
        self.items = items

        return items

    def get_paginated_response(self, data):
        """
        Cursor pagination response
        """
        return Response(OrderedDict([
            ('has_next', self.has_next),
            ('next_cursor', self.next_cursor),
            ('page_size', len(self.items)),
            ('results', data)
        ]))