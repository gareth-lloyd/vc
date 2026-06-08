"""Smoke test for `core.audit` model registration.

Every model whose business-logic docstring or anonymisation flow claims
an AuditLog trail must be registered in its app's `ready()` hook. This
test pins that contract so a future apps.py edit can't silently break
the compliance story.

If a model is intentionally dropped from the registry, update the
expected set here and explain why in the same commit — don't disable
the test.
"""

from __future__ import annotations

import pytest
from django.apps import apps

from core.audit import get_spec

EXPECTED_TRACKED_MODELS = {
    "accounts.Contact",
    "accounts.User",
    "comms.EmailLog",
    "comms.EmailTemplate",
    "comms.SmtpProfile",
    "integrations.OAuthCredential",
    "owners.OwnerMembership",
    "owners.OwnerOrgProperty",
    "owners.OwnerOrganisation",
    "payments.Payment",
    "payments.Refund",
    "properties.GroupFinance",
    "properties.PropertyFinance",
    "reservations.Booking",
    "reservations.BookingGuest",
    "reservations.BookingServiceCoverage",
    "reservations.Guest",
    "reservations.OwnerBlock",
    "reservations.QuotationLine",
}


@pytest.mark.parametrize("label", sorted(EXPECTED_TRACKED_MODELS))
def test_model_is_registered_for_audit(label: str) -> None:
    model = apps.get_model(label)
    spec = get_spec(model)
    assert spec is not None, (
        f"{label} is missing a `core.audit.track(...)` call in its app's "
        f"`ready()`. Either register it or remove it from "
        f"EXPECTED_TRACKED_MODELS with a CLAUDE.md note explaining why."
    )
    assert spec.fields, f"{label} is registered with an empty field list"
