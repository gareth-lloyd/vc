"""Tests for the `zoho_send_sample` management command.

The command builds a synthetic object graph exercising every enum-transmitting
Zoho Flow payload attribute, pushes each record to the `ZOHO_SAMPLE_WEBHOOK_*`
endpoints through the production pipeline, then rolls the data back. These tests
mock the HTTP transport (`integrations.tasks.httpx.post`) and set the sample
URLs via `monkeypatch.setenv`, then assert:

- enum coverage: every enum-transmitting attribute path is non-null in >=1
  captured payload (the core requirement);
- rollback: no synthetic rows survive;
- dry-run: no HTTP, payload JSON printed, DB unchanged;
- skip: a kind with an unset sample URL is reported and not pushed;
- guard: refuses to run when SEED_DEV_ALLOWED is False.
"""

from __future__ import annotations

from collections import defaultdict
from io import StringIO
from typing import Any
from unittest import mock

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import Person
from integrations import tasks
from integrations.models import SyncRecord
from properties.models.property import Property
from reservations.models import Booking, Enquiry, Quotation

# Distinct sample URLs per kind so a captured POST maps back to its kind.
_URLS = {
    "contact": "https://flow.test/sample/contact",
    "villa": "https://flow.test/sample/villa",
    "enquiry": "https://flow.test/sample/enquiry",
    "quote": "https://flow.test/sample/quote",
    "booking": "https://flow.test/sample/booking",
}
_URL_TO_KIND = {url: kind for kind, url in _URLS.items()}


def _response(status_code: int, url: str) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", url))


def _set_sample_env(monkeypatch: pytest.MonkeyPatch, kinds: set[str] | None = None) -> None:
    """Set the ZOHO_SAMPLE_WEBHOOK_* env vars (all kinds unless restricted)."""
    for kind, url in _URLS.items():
        var = f"ZOHO_SAMPLE_WEBHOOK_{kind.upper()}"
        if kinds is None or kind in kinds:
            monkeypatch.setenv(var, url)
        else:
            monkeypatch.delenv(var, raising=False)


def _run_capturing_posts(
    monkeypatch: pytest.MonkeyPatch, *args: str
) -> tuple[mock.Mock, dict[str, list[dict[str, Any]]], str]:
    """Run the command with a mocked transport; return (post_mock, payloads
    grouped by kind, stdout)."""

    def _post(url: str, **kwargs: Any) -> httpx.Response:
        return _response(200, url)

    post = mock.Mock(side_effect=_post)
    monkeypatch.setattr(tasks.httpx, "post", post)

    out = StringIO()
    call_command("zoho_send_sample", *args, stdout=out)

    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in post.call_args_list:
        url = call.args[0]
        by_kind[_URL_TO_KIND[url]].append(call.kwargs["json"])
    return post, by_kind, out.getvalue()


# ── enum coverage (the core requirement) ─────────────────────────────────


@pytest.mark.django_db
def test_every_enum_transmitting_attribute_is_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)
    _post, payloads, _out = _run_capturing_posts(monkeypatch)

    # Every kind produced at least one payload.
    for kind in _URLS:
        assert payloads[kind], f"no {kind} payload captured"

    # --- contact --------------------------------------------------------
    contacts = payloads["contact"]
    assert any(c["preferred_method"] for c in contacts)
    assert any(c["status"] for c in contacts)
    assert any(c["kind"] for c in contacts)
    assert any(c["tags"] for c in contacts)
    assert any(c["agency"] and c["agency"]["org_type"] for c in contacts)
    assert any(c["agency"] and c["agency"]["status"] for c in contacts)
    email_labels = {e["label"] for c in contacts for e in c["emails"]}
    assert len(email_labels) >= 2, email_labels
    phone_labels = {p["label"] for c in contacts for p in c["phones"]}
    assert {"mobile"} <= phone_labels and len(phone_labels) >= 2, phone_labels
    rel_kinds = {r["kind"] for c in contacts for r in c["relationships"]}
    rel_directions = {r["direction"] for c in contacts for r in c["relationships"]}
    rel_relations = {r["relation"] for c in contacts for r in c["relationships"]}
    assert "pa" in rel_kinds
    assert rel_directions == {"in", "out"}, rel_directions
    assert {"PA", "Principal"} <= rel_relations, rel_relations

    # --- villa ----------------------------------------------------------
    villa = payloads["villa"][0]
    assert villa["status"] and villa["channel"]
    roles = {c["role"] for c in villa["contacts"]}
    assert {"owner", "management_company"} <= roles, roles
    org_types = {c["organisation"]["org_type"] for c in villa["contacts"] if c["organisation"]}
    assert "mgmt" in org_types, org_types
    placements = {r["placement"] for r in villa["rooms"] if r["placement"]}
    floors = {r["floor"] for r in villa["rooms"] if r["floor"]}
    ensuites = {r["ensuite_type"] for r in villa["rooms"] if r["ensuite_type"]}
    accesses = {r["access"] for r in villa["rooms"] if r["access"]}
    assert placements and floors and ensuites and accesses
    bed_sizes = {
        r["beds"]["double_size"] for r in villa["rooms"] if r["beds"] and r["beds"]["double_size"]
    }
    assert bed_sizes, "no room bed size transmitted"
    service_types = {f["service_type"] for f in villa["features"]}
    assert {"amenity", "included_service", "paid_addon"} <= service_types, service_types

    # --- enquiry --------------------------------------------------------
    enquiries = payloads["enquiry"]
    assert any(e["contact_method"] for e in enquiries)
    assert any(e["request_type"] for e in enquiries)
    assert any(e["site_source"] for e in enquiries)
    assert any(e["status"] for e in enquiries)
    assert any(e["lead_status"] for e in enquiries)
    assert any(e["lost_reason"] for e in enquiries), "dead enquiry lost_reason missing"
    note_kinds = {n["kind"] for e in enquiries for n in e["notes"]}
    assert note_kinds, "no enquiry note kinds transmitted"

    # --- quote ----------------------------------------------------------
    assert payloads["quote"][0]["status"]

    # --- booking --------------------------------------------------------
    booking = payloads["booking"][0]
    assert booking["status"]
    assert booking["site_source"]
    assert booking["payment_method"]
    categories = {x["category"] for x in booking["extras"] if x["category"]}
    # Charge-only values AND a snapshot-sourced ExtraKind must both appear.
    assert {"damage", "credit"} <= categories, categories
    assert categories - {"damage", "credit"}, "no snapshot-sourced extra category"
    financials = booking["financials"]
    for key in (
        "total_gross",
        "gross_deposit",
        "net_deposit",
        "gross_balance",
        "net_balance",
    ):
        assert financials[key] is not None, f"financials.{key} is null"
    # GAP-099: the scheduler stamps due_at, so the end-to-end ISO path is live.
    assert financials["deposit_status"] is not None
    assert financials["deposit_due_at"] is not None


# ── rollback ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_command_rolls_back_all_synthetic_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)
    before = {
        "person": Person.objects.count(),
        "property": Property.objects.count(),
        "enquiry": Enquiry.objects.count(),
        "quotation": Quotation.objects.count(),
        "booking": Booking.objects.count(),
        "sync": SyncRecord.objects.count(),
    }

    _post, payloads, _out = _run_capturing_posts(monkeypatch)
    assert payloads["booking"]  # it really ran

    assert Person.objects.count() == before["person"]
    assert Property.objects.count() == before["property"]
    assert Enquiry.objects.count() == before["enquiry"]
    assert Quotation.objects.count() == before["quotation"]
    assert Booking.objects.count() == before["booking"]
    assert SyncRecord.objects.count() == before["sync"]


# ── dry-run ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_dry_run_prints_payloads_without_posting(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)
    before = Booking.objects.count()

    post, payloads, out = _run_capturing_posts(monkeypatch, "--dry-run")

    assert post.call_count == 0
    assert not any(payloads.values())
    assert "payload:" in out
    assert '"RES_ID"' in out
    assert Booking.objects.count() == before


# ── skip unset URL ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_kind_with_unset_sample_url_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Everything except booking.
    _set_sample_env(monkeypatch, kinds={"contact", "villa", "enquiry", "quote"})

    _post, payloads, out = _run_capturing_posts(monkeypatch)

    assert not payloads["booking"], "booking pushed despite unset URL"
    assert payloads["contact"], "other kinds should still push"
    assert "[booking] sample webhook URL unset — skipped" in out


# ── --kinds subset ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_kinds_option_restricts_pushes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--kinds", "contact,villa")

    assert payloads["contact"] and payloads["villa"]
    assert not payloads["enquiry"] and not payloads["booking"]


def test_kinds_option_rejects_unknown_kind() -> None:
    with pytest.raises(CommandError, match="Unknown kind"):
        call_command("zoho_send_sample", "--kinds", "contact,bogus")


# ── guard ────────────────────────────────────────────────────────────────


@override_settings(SEED_DEV_ALLOWED=False)
def test_guard_blocks_when_seed_dev_disallowed() -> None:
    with pytest.raises(CommandError, match="SEED_DEV_ALLOWED"):
        call_command("zoho_send_sample")
