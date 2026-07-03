"""GAP-046 Unit 5b — the company→agency backfill in migration 0012.

Migration ``0012`` runs ``_backfill_agency_from_company`` *before* dropping the
free-text ``Person.company`` column: every non-blank company string is folded
into a deduplicated ``Organisation(org_type="agency")`` and ``Person.agency`` is
linked. These tests drive that callable directly against the historical ``0011``
state where the ``company`` column still exists, plus a sync test pinning the
migration's FROZEN dedup-key helper against the live ``company_dedup_key`` so the
two implementations can never drift (a drift would mint duplicate orgs).

The data test mirrors ``reservations/tests/test_migration_0035_rekey_guest_mirror``:
roll ``accounts`` back to ``0011`` (re-creating the ``company`` column), seed via
the historical models, run the backfill, assert, then hard-delete via raw SQL and
migrate forward to the ``0012`` leaf so the ``transaction=True`` flush teardown is
clean.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState

from accounts.services.organisations import company_dedup_key

_APP = "accounts"
_BEFORE = "0011_person_agency"
_LEAF = "0012_drop_person_company"

# The migration module name starts with a digit, so it can't be a normal import.
_migration = importlib.import_module(f"accounts.migrations.{_LEAF}")


# ---------------------------------------------------------------------------
# Sync test — the frozen copy must equal the live algorithm for every input.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "Dune Travel",
        "  dune   TRAVEL ",  # case + whitespace variant → same key
        "Acme",
        "Ταξίδια Δία",  # non-Latin (Greek) — helper promises these survive
        "O'Brien & Co.",
    ],
)
def test_frozen_dedup_key_matches_live(name: str) -> None:
    """The migration's inlined `_frozen_company_dedup_key` must produce the
    IDENTICAL key to the live `company_dedup_key` — else a future edit to the
    live helper silently splits backfilled orgs from loader-created ones."""
    assert _migration._frozen_company_dedup_key(name) == company_dedup_key(name)


# ---------------------------------------------------------------------------
# Data test — drive the backfill against the live 0011 schema.
# ---------------------------------------------------------------------------
def _migrate(target: str) -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([(_APP, target)])
    executor.loader.build_graph()


def _historical_state() -> ProjectState:
    """Project state just before 0012 runs — `Person.company` still present."""
    loader = MigrationExecutor(connection).loader
    return loader.project_state(_migration.Migration.dependencies)


def _backfill(state: ProjectState) -> None:
    _migration._backfill_agency_from_company(state.apps, connection.schema_editor())


def _make_person(HPerson: Any, *, company: str, agency_id: int | None = None) -> Any:
    return HPerson.objects.create(
        first_name="Agent",
        last_name="Person",
        kind="contact",
        status="active",
        company=company,
        agency_id=agency_id,
    )


def _delete_rows(table: str, pks: list[int]) -> None:
    if not pks:
        return
    placeholders = ", ".join(["%s"] * len(pks))
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", pks)


@pytest.mark.django_db(transaction=True)
def test_backfill_links_dedupes_and_is_idempotent() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HPerson: Any = state.apps.get_model(_APP, "Person")
    HOrg: Any = state.apps.get_model(_APP, "Organisation")
    person_pks: list[int] = []
    org_pks: list[int] = []
    try:
        # A pre-existing agency + a Person already linked to it: the
        # `agency__isnull=True` filter must skip this row (never clobber a link).
        preexisting = HOrg.objects.create(name="Preexisting", org_type="agency", status="active")
        org_pks.append(preexisting.pk)

        p_dune = _make_person(HPerson, company="Dune Travel")
        p_dune_variant = _make_person(HPerson, company="  dune   TRAVEL ")  # dedup onto p_dune
        p_blank = _make_person(HPerson, company="   ")  # whitespace → no agency
        p_linked = _make_person(HPerson, company="Other Co", agency_id=preexisting.pk)
        person_pks += [p_dune.pk, p_dune_variant.pk, p_blank.pk, p_linked.pk]

        _backfill(state)
        for p in (p_dune, p_dune_variant, p_blank, p_linked):
            p.refresh_from_db()

        # The two casing/whitespace variants converge on ONE new agency org.
        dune_org = HOrg.objects.get(name="Dune Travel")
        org_pks.append(dune_org.pk)
        assert dune_org.org_type == "agency"
        assert dune_org.dedup_key == company_dedup_key("Dune Travel")
        assert p_dune.agency_id == dune_org.pk
        assert p_dune_variant.agency_id == dune_org.pk
        # Blank company → no org minted, agency stays null.
        assert p_blank.agency_id is None
        assert not HOrg.objects.filter(name="   ").exists()
        # Already-linked Person untouched; no "Other Co" org created.
        assert p_linked.agency_id == preexisting.pk
        assert not HOrg.objects.filter(name="Other Co").exists()
        # Exactly two orgs: the pre-existing one + the deduped Dune Travel.
        assert HOrg.objects.count() == 2

        # Idempotent: a second run finds no null-agency company rows → no change.
        _backfill(state)
        assert HOrg.objects.count() == 2
        p_dune.refresh_from_db()
        assert p_dune.agency_id == dune_org.pk
    finally:
        _delete_rows("accounts_person", person_pks)  # FK to org (PROTECT) → persons first
        _delete_rows("accounts_organisation", org_pks)
        # Rolling `accounts` (bottom of the dependency spine) back to 0011
        # cascades a project-wide reversal — every app that FKs into
        # accounts_user (pricing, reservations, …) is un-applied too. Restoring
        # only `accounts` would leave those reverted, so the transaction=True
        # flush teardown TRUNCATEs a half-reverted schema and fails, poisoning
        # the shared xdist worker DB. Restore the WHOLE project to its leaves.
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_forward_migration_drops_column_with_company_rows_present() -> None:
    """Migrating *forward* through 0012 must succeed even when company-bearing
    rows exist — the regression case the empty CI test DB never exercised.

    The backfill writes ``agency`` (a DEFERRABLE INITIALLY DEFERRED FK), queuing
    deferred trigger events; the following ``RemoveField`` then issues
    ``ALTER TABLE accounts_person DROP COLUMN company``. Without the migration's
    ``SET CONSTRAINTS ALL IMMEDIATE`` flush, Postgres raises "cannot ALTER TABLE
    ... because it has pending trigger events". Unlike the test above, this one
    leaves the rows in place across the forward migration — that's the point.
    """
    _migrate(_BEFORE)
    state = _historical_state()
    HPerson: Any = state.apps.get_model(_APP, "Person")
    person = _make_person(HPerson, company="Forward Travel Co")
    person_pk = person.pk

    try:
        # Forward migration runs backfill (writes deferred FK) *then* drops the
        # column in the same transaction — this is the line that used to blow up.
        _migrate(_LEAF)

        with connection.cursor() as cursor:
            cursor.execute("SELECT agency_id FROM accounts_person WHERE id = %s", [person_pk])
            (agency_id,) = cursor.fetchone()
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'accounts_person' AND column_name = 'company'"
            )
            company_column_exists = cursor.fetchone() is not None

        assert company_column_exists is False, "0012 should have dropped the company column"
        assert agency_id is not None, "backfill should have linked the person to an agency"

        _delete_rows("accounts_person", [person_pk])
        _delete_rows("accounts_organisation", [agency_id])
    finally:
        # `_migrate(_BEFORE)` reverted the whole project (see the sibling test);
        # `_migrate(_LEAF)` only restores `accounts`. Bring every app back to its
        # leaf so the transaction=True flush teardown TRUNCATEs a whole schema.
        call_command("migrate", verbosity=0)
