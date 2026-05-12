from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from core import views

router = DefaultRouter()
router.register(r"audit-log", views.AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("health", views.health, name="health"),
    path("health/", views.health, name="health-trailing"),
    path("health/ready", views.health_ready, name="health-ready"),
    path("system/version", views.system_version, name="system-version"),
    path("system/time", views.system_time, name="system-time"),
    path("system/settings", views.SystemSettingsView.as_view(), name="system-settings"),
    *router.urls,
]
