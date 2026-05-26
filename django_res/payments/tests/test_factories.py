"""Factory smoke tests for the payments app."""

from __future__ import annotations

from typing import cast

import pytest

from payments import factories, models

pytestmark = pytest.mark.django_db


def test_webhook_delivery_factory_unique_event_id_across_runs() -> None:
    w1 = cast(models.WebhookDelivery, factories.WebhookDeliveryFactory())
    w2 = cast(models.WebhookDelivery, factories.WebhookDeliveryFactory())
    # `(provider, event_id)` is unique; the RUN_TOKEN+Sequence must not
    # collide across additive seed runs.
    assert w1.event_id != w2.event_id
    assert w1.provider == w2.provider
