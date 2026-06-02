"""factory-boy factories for the `comms` app.

`SmtpProfileFactory` defaults to a SYSTEM-scoped profile with `is_active=False`
because the partial-unique constraint `one_active_system_smtp_profile` allows
only one active system profile at a time — additive seed runs collide
otherwise. Tests/seed stages that want the canonical active profile should
override `is_active=True` explicitly and only do so once per run.

`EmailTemplateFactory` similarly defaults `is_active=False` (partial-unique
`one_active_template_per_key`) and stamps the key with `RUN_TOKEN` to
sidestep the `(key, version)` unique constraint across re-runs.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from comms import models
from comms.enums import SmtpScope
from core.factories import RUN_TOKEN


class SmtpProfileFactory(DjangoModelFactory):
    class Meta:
        model = models.SmtpProfile

    name = factory.Sequence(lambda n: f"SMTP {RUN_TOKEN}-{n}")
    scope = SmtpScope.SYSTEM
    owner = None
    host = "smtp.example.com"
    port = 587
    username = factory.Sequence(lambda n: f"smtp-user-{RUN_TOKEN}-{n}")
    encrypted_password = "seedpw"
    use_tls = True
    from_email = factory.Sequence(lambda n: f"noreply-{RUN_TOKEN}-{n}@example.com")
    # Default off so additive runs do not violate `one_active_system_smtp_profile`.
    is_active = False


class EmailTemplateFactory(DjangoModelFactory):
    class Meta:
        model = models.EmailTemplate

    key = factory.Sequence(lambda n: f"template-{RUN_TOKEN}-{n}")
    version = 1
    subject_template = "Seed subject"
    body_template = "Plaintext seed body"
    # A trivially-valid MJML doc keeps `EmailTemplate.save`'s compile-on-save
    # cheap; the resulting HTML lands in `body_template_html` automatically.
    body_template_mjml = "<mjml><mj-body><mj-text>Seed</mj-text></mj-body></mjml>"
    notes = "seeded by factory"
    is_active = False
