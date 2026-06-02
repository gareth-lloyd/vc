"""Shared `:status-counts` action for list endpoints with a `status` filter.

Powers the frontend's status tab-bar count badges: one aggregate query
returning ``{status: count}`` for the current filter set, so the SPA never
fans out one count request per status.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response


class StatusCountsMixin:
    """Adds ``GET {collection}/status-counts`` to a filtered list viewset.

    Counts honour every active filter *except* ``status`` (so the bar can show
    how many rows each status holds within the current search / date scope),
    and are grouped on the model's ``status`` column.
    """

    filterset_class: type
    get_queryset: Any

    @action(detail=False, methods=["get"], url_path="status-counts")
    def status_counts(self, request: Request) -> Response:
        params = request.query_params.copy()
        params.pop("status", None)
        filtered = self.filterset_class(params, queryset=self.get_queryset(), request=request).qs
        rows = filtered.values("status").annotate(n=Count("id"))
        return Response({row["status"]: row["n"] for row in rows})
