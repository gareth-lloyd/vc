from __future__ import annotations

from django.urls import URLPattern, URLResolver
from rest_framework.routers import DefaultRouter

from comms.views import EmailLogViewSet, EmailTemplateViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"email-logs", EmailLogViewSet, basename="email-log")

# Template keys are dotted (`booking.confirmation`). The viewset widens
# `lookup_value_regex` to admit dots; the router must also drop the optional
# `.format` suffix it appends, or `booking.confirmation` would be parsed as
# key=`booking`, format=`confirmation` (C2). A dedicated router keeps the
# email-logs routes (which want the default behaviour) untouched.
template_router = DefaultRouter(trailing_slash=False)
template_router.include_format_suffixes = False
template_router.register(r"email-templates", EmailTemplateViewSet, basename="email-template")

urlpatterns: list[URLPattern | URLResolver] = [*router.urls, *template_router.urls]
