"""factory-boy factories for the `payments` app.

`WebhookDelivery` is keyed by `(provider, event_id)`. The event_id must
be globally unique across additive seed runs, so the factory combines
the per-process `RUN_TOKEN` with a sequence — without the token a second
seed_dev run collides on the unique constraint.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from core.factories import RUN_TOKEN
from payments import models
from payments.enums import WebhookProvider


class WebhookDeliveryFactory(DjangoModelFactory):
    class Meta:
        model = models.WebhookDelivery

    provider = WebhookProvider.STRIPE
    event_id = factory.Sequence(lambda n: f"evt_{RUN_TOKEN}_{n}")
    signature = ""
    signature_valid = True
    raw_body = "{}"
    headers = factory.LazyFunction(dict)
