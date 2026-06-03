"""URL routing for the owner portal (`/owner/*`)."""

from __future__ import annotations

from django.urls import path

from owners.views.me import OwnerMeView
from owners.views.properties import OwnerPropertyViewSet

urlpatterns = [
    path("owner/me", OwnerMeView.as_view(), name="owner-me"),
    path(
        "owner/properties",
        OwnerPropertyViewSet.as_view({"get": "list"}),
        name="owner-property-list",
    ),
    path(
        "owner/properties/<int:pk>",
        OwnerPropertyViewSet.as_view({"get": "retrieve"}),
        name="owner-property-detail",
    ),
]
