"""Factory smoke tests for the comms app."""

from __future__ import annotations

from typing import cast

import pytest

from comms import factories, models

pytestmark = pytest.mark.django_db


def test_smtp_profile_factory_roundtrips() -> None:
    p1 = cast(models.SmtpProfile, factories.SmtpProfileFactory())
    p2 = cast(models.SmtpProfile, factories.SmtpProfileFactory())
    assert p1.pk != p2.pk
    assert p1.host == "smtp.example.com"
    # Default off so the active-system unique constraint allows additive runs.
    assert p1.is_active is False


def test_email_template_factory_compiles_mjml() -> None:
    t = cast(models.EmailTemplate, factories.EmailTemplateFactory())
    assert t.pk is not None
    # MJML compile-on-save fills body_template_html.
    assert t.body_template_html
    assert t.is_active is False
