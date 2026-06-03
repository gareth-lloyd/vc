"""URL routing for the owner portal (`/owner/*`)."""

from __future__ import annotations

from django.urls import path

from owners.views.me import OwnerMeView

urlpatterns = [
    path("owner/me", OwnerMeView.as_view(), name="owner-me"),
]
