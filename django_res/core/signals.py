"""Audit middleware companion: populate created_by/updated_by on save."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver

from core.request_context import get_current_user


@receiver(pre_save, dispatch_uid="core.audit.populate_user_fields")
def populate_user_fields(sender: type[models.Model], instance: models.Model, **_: Any) -> None:
    field_names = {f.name for f in sender._meta.get_fields() if hasattr(f, "attname")}
    if "created_by" not in field_names or "updated_by" not in field_names:
        return
    user = get_current_user()
    if user is None:
        return
    if instance.pk is None and getattr(instance, "created_by_id", None) is None:
        instance.created_by = user  # type: ignore[attr-defined]
    instance.updated_by = user  # type: ignore[attr-defined]
