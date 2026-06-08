"""C1 backstop: a malformed active template must not abort a domain transition.

The publish API render-validates a template before it can go active, but a row
created out-of-band (fixture, shell, bulk import) could still carry a broken
Django tag. `comms.signals._safe_send` must degrade such a send to a logged
skip rather than letting the `TemplateSyntaxError` propagate out of the signal
handler and roll back the booking/payment transition that triggered it.
"""

from __future__ import annotations

import pytest

from comms.models import EmailTemplate, SmtpProfile
from comms.signals import _safe_send


@pytest.mark.django_db
def test_safe_send_swallows_template_syntax_error(system_profile: SmtpProfile) -> None:
    EmailTemplate.objects.create(
        key="test.malformed",
        version=1,
        # `{% if %}` with no condition is a TemplateSyntaxError at render time;
        # the model's MJML compile-on-save doesn't catch Django template syntax,
        # so this row goes active just fine — exactly the hazard C1 guards.
        subject_template="Broken {% if %}{{ booking_reference }}",
        body_template="Hi",
    )

    # Must not raise — the transition that called this stays committed.
    _safe_send(
        template_key="test.malformed",
        context={"booking_reference": "VC-1"},
        to=["guest@example.com"],
    )
