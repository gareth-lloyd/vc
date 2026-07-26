"""URLs for the inbound WordPress surface (`/api/wordpress/*`).

Separate from the staff `/api/v1/` tree so the token-authed service-user
surface stays a distinct subtree (08-integrations.md §Endpoint surface).
Paths are pinned WITHOUT a trailing slash (router convention); APPEND_SLASH
cannot redirect a POST, so the wrong variant 404s loudly.
"""

from __future__ import annotations

from django.urls import path

from reservations.views.wordpress import WordPressEnquiryView

urlpatterns = [
    path("enquiries", WordPressEnquiryView.as_view(), name="wordpress-enquiries"),
]
