from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from comms.exceptions import MjmlCompileError
from comms.management.commands.seed_email_templates import (
    discover_seeds,
    sync_templates,
)
from comms.models import EmailTemplate

SIMPLE_MJML = (
    "<mjml><mj-body><mj-section><mj-column>"
    "<mj-text>Hello {{ name }}</mj-text>"
    "</mj-column></mj-section></mj-body></mjml>"
)


def _write_seed(directory: Path, key: str, *, subject: str, body: str, mjml: str = "") -> None:
    (directory / f"{key}.subject.txt").write_text(subject)
    (directory / f"{key}.body.txt").write_text(body)
    if mjml:
        (directory / f"{key}.body.mjml").write_text(mjml)


def test_discover_seeds_reads_subject_body_and_mjml(tmp_path: Path) -> None:
    _write_seed(
        tmp_path,
        "test.seed.simple",
        subject="Your code\n",
        body="Code: {{ code }}\n",
        mjml=SIMPLE_MJML,
    )
    seeds = discover_seeds(tmp_path)

    assert len(seeds) == 1
    assert seeds[0].key == "test.seed.simple"
    assert seeds[0].subject == "Your code"
    assert seeds[0].body_text == "Code: {{ code }}\n"
    assert seeds[0].body_mjml == SIMPLE_MJML


@pytest.mark.django_db
def test_sync_creates_missing_templates(tmp_path: Path) -> None:
    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Body", mjml=SIMPLE_MJML)

    result = sync_templates(tmp_path)

    assert result == {"created": 1, "updated": 0, "unchanged": 0}
    template = EmailTemplate.objects.get(key="test.seed.simple", is_active=True)
    assert template.version == 1
    assert template.subject_template == "Code"
    assert template.body_template == "Body"
    assert template.body_template_mjml == SIMPLE_MJML
    assert "Hello {{ name }}" in template.body_template_html


@pytest.mark.django_db
def test_sync_is_idempotent_when_content_matches(tmp_path: Path) -> None:
    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Body", mjml=SIMPLE_MJML)

    sync_templates(tmp_path)
    second = sync_templates(tmp_path)

    assert second == {"created": 0, "updated": 0, "unchanged": 1}
    assert EmailTemplate.objects.filter(key="test.seed.simple").count() == 1


@pytest.mark.django_db
def test_sync_bumps_version_when_content_changes(tmp_path: Path) -> None:
    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Body", mjml=SIMPLE_MJML)
    sync_templates(tmp_path)

    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Updated body", mjml=SIMPLE_MJML)
    result = sync_templates(tmp_path)

    assert result == {"created": 0, "updated": 1, "unchanged": 0}
    versions = list(
        EmailTemplate.objects.filter(key="test.seed.simple")
        .order_by("version")
        .values("version", "is_active", "body_template")
    )
    assert versions == [
        {"version": 1, "is_active": False, "body_template": "Body"},
        {"version": 2, "is_active": True, "body_template": "Updated body"},
    ]


@pytest.mark.django_db
def test_sync_aborts_on_invalid_mjml_with_no_partial_write(tmp_path: Path) -> None:
    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Body", mjml=SIMPLE_MJML)
    _write_seed(tmp_path, "test.seed.broken", subject="Bad", body="Bad", mjml="<not-mjml/>")

    with pytest.raises(MjmlCompileError):
        sync_templates(tmp_path)

    assert not EmailTemplate.objects.filter(key__startswith="test.seed.").exists()


@pytest.mark.django_db
def test_sync_handles_template_without_mjml(tmp_path: Path) -> None:
    _write_seed(tmp_path, "test.seed.plainonly", subject="Plain", body="Plaintext only")

    sync_templates(tmp_path)

    template = EmailTemplate.objects.get(key="test.seed.plainonly", is_active=True)
    assert template.body_template_mjml == ""
    assert template.body_template_html == ""


@pytest.mark.django_db
def test_management_command_invokes_sync_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_seed(tmp_path, "test.seed.simple", subject="Code", body="Body", mjml=SIMPLE_MJML)
    monkeypatch.setattr(
        "comms.management.commands.seed_email_templates._seed_dir",
        lambda base_dir=None: tmp_path,
    )

    out = StringIO()
    call_command("seed_email_templates", stdout=out)

    assert "1 created" in out.getvalue()
    assert EmailTemplate.objects.filter(key="test.seed.simple").exists()


@pytest.mark.django_db
def test_disk_seeds_are_present_after_migration() -> None:
    """Every on-disk seed exists as an active EmailTemplate after migrate.

    The seed data migration runs at test-DB setup, so a re-sync here should be
    a pure no-op — every seed is already present and unchanged.
    """
    result = sync_templates()
    seeds = discover_seeds()

    assert result == {"created": 0, "updated": 0, "unchanged": len(seeds)}
    for seed in seeds:
        template = EmailTemplate.objects.get(key=seed.key, is_active=True)
        if seed.body_mjml:
            assert template.body_template_html, f"{seed.key} has MJML but produced no HTML"
