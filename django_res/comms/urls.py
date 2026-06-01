from __future__ import annotations

from django.urls import URLPattern, URLResolver
from rest_framework.routers import DefaultRouter

from comms.views import EmailLogViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"email-logs", EmailLogViewSet, basename="email-log")

urlpatterns: list[URLPattern | URLResolver] = [*router.urls]
