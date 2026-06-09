"""Shared pagination classes."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class ConfigurablePageSizePagination(PageNumberPagination):
    """`PageNumberPagination` that lets a client raise the page size.

    Reference lookups (e.g. the ~250-row country list) need every row in one
    request to populate a `<Select>`; the default fixed page size would
    silently truncate them. `max_page_size` keeps the override bounded.
    """

    page_size_query_param = "page_size"
    max_page_size = 500
