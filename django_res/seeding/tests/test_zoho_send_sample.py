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
from decimal import Decimal
from io import StringIO
from typing import Any
from unittest import mock

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.enums import OrgType
from accounts.models import Person
from integrations import tasks
from integrations.models import SyncRecord
from properties.models.property import Property
from reservations.models import Booking, Enquiry, Quotation

# Distinct sample URLs per kind so a captured POST maps back to its kind.
_URLS = {
    "organisation": "https://flow.test/sample/organisation",
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

    # --- organisation ---------------------------------------------------
    organisations = payloads["organisation"]
    owner_org_types = {o["org_type"] for o in organisations}
    assert {
        OrgType.AGENCY.value,
        OrgType.MANAGEMENT_COMPANY.value,
    } <= owner_org_types, owner_org_types
    assert all(o["status"] for o in organisations)
    # Both country branches on the wire: baseline's agency carries one, the
    # management company does not.
    assert any(o["country"] for o in organisations)
    assert any(o["country"] is None for o in organisations)
    assert any(o["notes"] for o in organisations)

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
    # GAP-102: the extras catalogue rides the villa push.
    extra_categories = {e["category"] for e in villa["extras"]}
    assert {"cleaning", "heating"} <= extra_categories, extra_categories
    extra_calcs = {e["calc"] for e in villa["extras"]}
    assert {"fixed_per_stay"} <= extra_calcs, extra_calcs
    service_types = {f["service_type"] for f in villa["features"]}
    assert {"amenity", "included_service", "paid_addon"} <= service_types, service_types
    # GAP-091: other-information tags ride their own block, never `features[]`.
    other = villa["other_information"]
    assert [t["slug"] for t in other["tags"]] == ["pets-allowed"], other
    assert other["description"], other
    assert "pets-allowed" not in {f["slug"] for f in villa["features"]}

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
    # GAP-102: the only real-engine path — pins that the engine's snapshot
    # `extra_id` key is what the payload reads as `RES_ID` (a hand-written
    # snapshot literal in the unit tests can't catch a key rename).
    engine_rows = [x for x in booking["extras"] if x["source"] == "extra"]
    assert engine_rows and all(isinstance(x["RES_ID"], int) for x in engine_rows)
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
    # GAP-102: the printed envelope is what the wire would carry — `_meta`
    # included, with no SyncRecord behind a dry run.
    assert '"_meta"' in out
    assert '"source": "res"' in out
    assert '"sync_record_id": null' in out
    assert Booking.objects.count() == before


# ── skip unset URL ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_kind_with_unset_sample_url_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Everything except booking (and organisation, which this test does not
    # exercise — the skip path is kind-agnostic).
    _set_sample_env(monkeypatch, kinds={"contact", "villa", "enquiry", "quote"})

    _post, payloads, out = _run_capturing_posts(monkeypatch)

    assert not payloads["booking"], "booking pushed despite unset URL"
    assert payloads["contact"], "other kinds should still push"
    assert "[baseline/booking] sample webhook URL unset — skipped" in out


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


# ── --scenarios subset ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_push_output_is_scenario_prefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)

    _post, _payloads, out = _run_capturing_posts(monkeypatch)

    assert "[baseline/villa] pk=" in out


@pytest.mark.django_db
def test_scenarios_baseline_is_what_a_bare_run_does(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "baseline")

    assert {kind for kind, sent in payloads.items() if sent} == set(_URLS)


@pytest.mark.django_db
def test_scenarios_all_includes_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, out = _run_capturing_posts(monkeypatch, "--scenarios", "all")

    assert payloads["villa"], "baseline must be part of --scenarios all"
    assert "[baseline/villa] pk=" in out


def test_scenarios_option_rejects_unknown_scenario() -> None:
    with pytest.raises(CommandError, match="Unknown scenario"):
        call_command("zoho_send_sample", "--scenarios", "baseline,bogus")


def test_scenarios_option_rejects_a_typo_alongside_all() -> None:
    # `all` must not short-circuit validation, or a misspelt name is swallowed.
    with pytest.raises(CommandError, match="Unknown scenario"):
        call_command("zoho_send_sample", "--scenarios", "all,bogus")


@pytest.mark.django_db
def test_separator_only_scenarios_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Not a silent zero-record run reporting success.
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", ",")

    assert payloads["villa"]


# ── shape scenarios ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_repush_scenario_sends_each_record_twice_mutated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only scenario in which an *update* is observable at all."""
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "repush")

    villas = payloads["villa"]
    assert len(villas) == 2, "the villa must be pushed twice — that is the scenario"
    assert villas[0]["RES_ID"] == villas[1]["RES_ID"], "same record, not two"
    assert villas[0]["display_name"] != villas[1]["display_name"], (
        "an unmutated re-push proves nothing about upsert vs insert"
    )

    bookings = payloads["booking"]
    assert len(bookings) == 2
    assert bookings[0]["RES_ID"] == bookings[1]["RES_ID"]
    assert bookings[0]["site_source"] != bookings[1]["site_source"]


@pytest.mark.django_db
def test_status_transitions_scenario_sends_each_lifecycle_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "status_transitions")

    quote_statuses = {q["status"] for q in payloads["quote"]}
    assert {"sent", "accepted", "cancelled"} <= quote_statuses, quote_statuses

    # The enquiry moves too — and `accept()` converts it through its own
    # instance, so a stale in-memory copy would silently push NEW twice.
    enquiry_statuses = {e["status"] for e in payloads["enquiry"]}
    assert {"new", "quote_sent", "converted"} <= enquiry_statuses, enquiry_statuses

    booking_statuses = [b["status"] for b in payloads["booking"]]
    assert "cancelled" in booking_statuses, booking_statuses
    assert len(set(booking_statuses)) >= 2, (
        f"a booking pushed only at one status shows no transition: {booking_statuses}"
    )


@pytest.mark.django_db
def test_a_shape_scenario_running_first_does_not_move_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline's records must be identical whatever else runs, and in whatever
    order — they are what Limitless has already mapped.

    Pinned to two scenarios on purpose: `--scenarios all` would drag every
    future scenario into a test that asserts nothing about them, and report
    their failures as baseline failures.
    """
    _set_sample_env(monkeypatch)

    # repush FIRST — the ordering that exposes shared-factory iterator drift.
    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "repush,baseline")

    baseline_villas = [
        v for v in payloads["villa"] if v["display_name"] == "Synthetic Sample Villa"
    ]
    assert len(baseline_villas) == 1, [v["display_name"] for v in payloads["villa"]]
    assert baseline_villas[0]["region"]["country"]["iso2"] == "GB"

    baseline_lines = [
        line
        for quote in payloads["quote"]
        for line in quote["lines"]
        if line["property"]["display_name"] == "Synthetic Sample Villa"
    ]
    assert baseline_lines, "no baseline quote line captured"
    assert baseline_lines[0]["currency"] == "GBP"
    # Money too: `RateBandFactory.nightly` is iterator-drawn, so an unpinned
    # rate would move baseline's line total — and every booking financials
    # figure with it — according to how many villas were built first.
    bare_post, bare_payloads, _bare_out = _run_capturing_posts(monkeypatch)
    bare_lines = [
        line
        for quote in bare_payloads["quote"]
        for line in quote["lines"]
        if line["property"]["display_name"] == "Synthetic Sample Villa"
    ]
    assert baseline_lines[0]["total"] == bare_lines[0]["total"], (
        f"baseline's money moved: {bare_lines[0]['total']} bare vs "
        f"{baseline_lines[0]['total']} after another scenario"
    )
    assert bare_post.call_count  # the bare run really executed


@pytest.mark.django_db
def test_multi_option_quote_scenario_sends_three_lines_one_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "multi_option_quote")

    lines = payloads["quote"][-1]["lines"]
    assert len(lines) == 3, f"a one-line quote is the shape we already had: {len(lines)}"
    assert sum(1 for line in lines if line["is_selected"]) == 1, lines


@pytest.mark.django_db
def test_discounted_scenario_sends_a_non_zero_line_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Asserted on the QUOTE, never the booking: BUG-020 loses the discount on
    # conversion, and this scenario demonstrates that rather than depending on
    # its fix.
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "discounted")

    lines = [line for quote in payloads["quote"] for line in quote["lines"]]
    discounted = [line for line in lines if Decimal(line["discount"]) > 0]
    assert discounted, [line["discount"] for line in lines]
    line = discounted[0]
    assert Decimal(line["total"]) > 0, "a discount must not zero the line"
    assert Decimal(line["pricing_snapshot"]["gross"]) - Decimal(line["discount"]) == Decimal(
        line["total"]
    )


@pytest.mark.django_db
def test_mixed_currency_scenario_sends_two_currencies_in_one_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "mixed_currency")

    lines = payloads["quote"][-1]["lines"]
    assert len({line["currency"] for line in lines}) == 2, [line["currency"] for line in lines]


@pytest.mark.django_db
def test_sparse_financials_scenario_sends_a_booking_with_null_financials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manual quotation line leaves `pricing_snapshot` empty, so every owner
    money figure is null — the shape a spreadsheet-imported booking will have."""
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "sparse_financials")

    financials = payloads["booking"][-1]["financials"]
    # Every key is still PRESENT — the block degrades to explicit nulls, it is
    # never omitted or invented as zeros (GAP-085). Asserted as a superset so
    # GAP-099-style additions to `_FINANCIALS_KEYS` don't break this test.
    assert {
        "total_gross",
        "total_net",
        "gross_deposit",
        "net_deposit",
        "deposit_commission",
        "gross_balance",
        "net_balance",
        "balance_commission",
    } <= set(financials), sorted(financials)
    assert all(value is None for value in financials.values()), financials


@pytest.mark.django_db
def test_anonymised_person_scenario_stops_pushing_after_erasure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This scenario proves an ABSENCE: after `Person.anonymize()` the pipeline
    parks the record DISABLED and sends nothing, so the CRM keeps the
    pre-erasure name forever. GAP-095's hole, made visible."""
    _set_sample_env(monkeypatch)

    _post, payloads, out = _run_capturing_posts(monkeypatch, "--scenarios", "anonymised_person")

    assert len(payloads["contact"]) == 1, (
        f"the erased person must not be POSTed a second time: {payloads['contact']}"
    )
    assert "[REDACTED]" not in str(payloads["contact"]), "erased PII must never be sent"
    assert "-> DISABLED" in out, out


@pytest.mark.django_db
def test_agency_only_contact_scenario_sends_a_contact_with_no_personal_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "agency_only_contact")

    nameless = [
        c for c in payloads["contact"] if not c["last_name"] and c["agency"] and c["agency"]["name"]
    ]
    assert nameless, [(c["last_name"], c["agency"]) for c in payloads["contact"]]


@pytest.mark.django_db
def test_villa_churn_scenario_sends_a_villa_that_lost_a_room_and_changed_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    _post, payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "villa_churn")

    before, after = payloads["villa"]
    assert len(after["rooms"]) == len(before["rooms"]) - 1, (
        f"{len(before['rooms'])} -> {len(after['rooms'])} rooms"
    )

    def _managers(villa: dict[str, Any]) -> set[str]:
        return {
            c["organisation"]["name"]
            for c in villa["contacts"]
            if c["role"] == "management_company" and c["organisation"] and c["end_date"] is None
        }

    assert _managers(before) and _managers(after)
    assert _managers(before) != _managers(after), _managers(after)
    # The superseded assignment is still on the wire, end-dated — the shape
    # that lets an ended row beat the current one if the Flow ignores dates.
    ended = [c for c in after["contacts"] if c["end_date"] is not None]
    assert ended, after["contacts"]


@pytest.mark.django_db
def test_out_of_order_scenario_sends_the_booking_before_its_villa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_sample_env(monkeypatch)

    post, _payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "out_of_order")

    order = [_URL_TO_KIND[call.args[0]] for call in post.call_args_list]
    assert order.index("booking") < order.index("villa"), order


@pytest.mark.django_db
def test_baseline_pushes_organisations_before_anything_nesting_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAP-096: the organisation steps exist ONLY for their position. The
    contact payload nests `agency` and the villa payload nests each
    contact's `organisation`, so both Accounts must already exist — that is
    what makes CHECK-001 / CHECK-003 able to tell a lookup from an inline
    create. Set-membership assertions elsewhere are order-blind and would
    stay green if these yields drifted down the scenario."""
    _set_sample_env(monkeypatch)

    post, _payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "baseline")

    order = [_URL_TO_KIND[call.args[0]] for call in post.call_args_list]
    last_organisation = max(i for i, kind in enumerate(order) if kind == "organisation")
    assert last_organisation < order.index("contact"), order
    assert last_organisation < order.index("villa"), order


@pytest.mark.django_db
def test_villa_churn_pushes_each_management_company_before_its_villa_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both halves of the churn: the outgoing management company precedes the
    first villa push, the incoming one precedes the second. A Flow that picks
    the superseded assignment (CHECK-003 item 2) then shows up as a villa
    linked to the WRONG Account rather than to a missing one."""
    _set_sample_env(monkeypatch)

    post, _payloads, _out = _run_capturing_posts(monkeypatch, "--scenarios", "villa_churn")

    order = [_URL_TO_KIND[call.args[0]] for call in post.call_args_list]
    organisations = [i for i, kind in enumerate(order) if kind == "organisation"]
    villas = [i for i, kind in enumerate(order) if kind == "villa"]
    assert len(organisations) == 2 and len(villas) == 2, order
    assert organisations[0] < villas[0], order
    assert organisations[1] < villas[1], order


@pytest.mark.django_db
def test_every_scenario_runs_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--scenarios all` is what an operator fires at the live sample flows.

    The per-scenario tests each run one scenario in isolation, so nothing else
    catches the cross-scenario failure class: a shared unique slug, an
    overlapping booking on a reused property, a factory minting an unreaped
    image. This is the cheap smoke test for that.
    """
    _set_sample_env(monkeypatch)

    _post, payloads, out = _run_capturing_posts(monkeypatch, "--scenarios", "all")

    for kind in _URLS:
        assert payloads[kind], f"no {kind} payload under --scenarios all"
    assert "done — synthetic data rolled back" in out
    assert SyncRecord.objects.count() == 0, "synthetic sync records survived the rollback"


# ── guard ────────────────────────────────────────────────────────────────


@override_settings(SEED_DEV_ALLOWED=False)
def test_guard_blocks_when_seed_dev_disallowed() -> None:
    with pytest.raises(CommandError, match="SEED_DEV_ALLOWED"):
        call_command("zoho_send_sample")
