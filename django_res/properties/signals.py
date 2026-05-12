from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from properties.models.finance import GroupFinance
from properties.models.property import PropertyGroup
from properties.models.settings import GroupSettings


@receiver(post_save, sender=PropertyGroup, dispatch_uid="properties.create_group_settings")
def create_group_settings(
    sender: type[PropertyGroup],
    instance: PropertyGroup,
    created: bool,
    **kwargs: Any,
) -> None:
    """Ensure every `PropertyGroup` has an attached `GroupSettings` row.

    Created with defaults on `PropertyGroup` insert; the row lives for the
    group's lifetime (CASCADE on delete).
    """
    if not created:
        return
    GroupSettings.objects.get_or_create(group=instance)


@receiver(post_save, sender=PropertyGroup, dispatch_uid="properties.create_group_finance")
def create_group_finance(
    sender: type[PropertyGroup],
    instance: PropertyGroup,
    created: bool,
    **kwargs: Any,
) -> None:
    """Ensure every `PropertyGroup` has an attached `GroupFinance` row."""
    if not created:
        return
    GroupFinance.objects.get_or_create(group=instance)
