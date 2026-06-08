from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from comms.exceptions import MjmlCompileError
from comms.models import EmailTemplate

VALID_MJML = (
    "<mjml><mj-body><mj-section><mj-column>"
    "<mj-text>Hello {{ name }}</mj-text>"
    "</mj-column></mj-section></mj-body></mjml>"
)


@pytest.mark.django_db
def test_unique_active_template_per_key() -> None:
    EmailTemplate.objects.create(
        key="test.fixture.template",
        version=1,
        subject_template="Confirmed",
        title="Hi",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EmailTemplate.objects.create(
            key="test.fixture.template",
            version=2,
            subject_template="Confirmed v2",
            title="Hi v2",
        )


@pytest.mark.django_db
def test_inactive_versions_coexist() -> None:
    EmailTemplate.objects.create(
        key="test.fixture.template",
        version=1,
        subject_template="v1",
        title="v1",
        is_active=False,
    )
    # New active row is allowed because no other row for this key is active.
    EmailTemplate.objects.create(
        key="test.fixture.template",
        version=2,
        subject_template="v2",
        title="v2",
        is_active=True,
    )


@pytest.mark.django_db
def test_unique_key_version_pair() -> None:
    EmailTemplate.objects.create(
        key="test.fixture.template",
        version=1,
        subject_template="v1",
        title="v1",
        is_active=False,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EmailTemplate.objects.create(
            key="test.fixture.template",
            version=1,
            subject_template="dup",
            title="dup",
            is_active=False,
        )


@pytest.mark.django_db
def test_save_compiles_mjml_to_html() -> None:
    template = EmailTemplate.objects.create(
        key="test.fixture.template",
        version=1,
        subject_template="Confirmed",
        title="Hi",
        body_template_mjml=VALID_MJML,
    )
    assert "<!doctype html>" in template.body_template_html.lower()
    assert "Hello {{ name }}" in template.body_template_html


@pytest.mark.django_db
def test_save_clears_html_when_mjml_blank() -> None:
    template = EmailTemplate.objects.create(
        key="test.fixture.template",
        version=1,
        subject_template="Confirmed",
        title="Hi",
        body_template_mjml=VALID_MJML,
    )
    assert template.body_template_html

    template.body_template_mjml = ""
    template.save()
    template.refresh_from_db()
    assert template.body_template_html == ""


@pytest.mark.django_db
def test_save_with_invalid_mjml_raises_and_does_not_persist() -> None:
    with pytest.raises(MjmlCompileError):
        EmailTemplate.objects.create(
            key="test.fixture.template",
            version=1,
            subject_template="Confirmed",
            title="Hi",
            body_template_mjml="<not-mjml/>",
        )
    assert not EmailTemplate.objects.filter(key="test.fixture.template").exists()
