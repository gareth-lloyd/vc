from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from properties.models.features import Collection
from properties.models.finance import GroupFinance
from properties.models.images import PropertyImage
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


@receiver(post_delete, sender=PropertyImage, dispatch_uid="properties.delete_image_file")
def delete_property_image_file(
    sender: type[PropertyImage],
    instance: PropertyImage,
    **kwargs: Any,
) -> None:
    """Release the stored file when a `PropertyImage` row is hard-deleted.

    Rows are hard-deleted (no soft delete), so without this the object would
    leak in storage forever — and S3 bills per stored byte. Storage `delete`
    is a no-op for a missing file (e.g. a legacy key whose binary was never
    imported), so this never raises for file-less rows.
    """
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=Collection, dispatch_uid="properties.delete_collection_cover")
def delete_collection_cover_file(
    sender: type[Collection],
    instance: Collection,
    **kwargs: Any,
) -> None:
    """Release the stored cover file when a `Collection` row is hard-deleted."""
    if instance.cover_image:
        instance.cover_image.delete(save=False)
