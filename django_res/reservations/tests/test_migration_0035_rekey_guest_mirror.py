"""GAP-045 D5-4c — the guest-mirror re-key in migration 0035.

Migration ``0035`` runs ``_rekey_forward`` *before* dropping the ``Guest``
model: every ``accounts.Person`` keyed ``guest-{Guest.pk}`` (a Guest→Person
mirror) is re-keyed onto the unified customer namespace
``client-{Guest.legacy_id}`` (the legacy ``VillaClientDetails.Id``). These
tests drive the ``_rekey_forward`` callable directly against the historical
state where the ``Guest`` table still exists, covering every branch:

1. normal re-key (``guest-{pk}`` with Guest.legacy_id="500" → "client-500");
2. NULL source (Guest.legacy_id is NULL / no Guest row → Person.legacy_id NULL,
   never the literal "client-None");
3. malformed key guard (``guest-abc`` suffix not ``.isdigit()`` → untouched);
4. idempotency (a second run finds no ``guest-`` rows, changes nothing);
5. fail-closed collision (two mirrors whose Guests share a legacy_id → the
   second target ``client-500`` already exists → ``RuntimeError``).

Each test rolls ``reservations`` back to ``0034`` (re-creating the ``Guest``
table + ``guest`` FKs), seeds via the historical models, calls
``_rekey_forward`` directly, asserts, then in ``finally`` deletes everything it
created (raw SQL — the historical ``properties`` state still carries columns
the live leaf schema has dropped, so an ORM cascade-delete collector would
SELECT a non-existent column) and migrates ``reservations`` forward to the
``0035`` LEAF so the ``transaction=True`` flush teardown is clean (no repeat of
the ``test_migration_0017`` teardown-to-a-non-leaf bug).
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState

_APP = "reservations"
_BEFORE = "0034_person_authoritative"
_LEAF = "0035_remove_guestpreference_guest_remove_booking_guest_and_more"

# The migration module name starts with a digit, so it can't be a normal import.
_migration = importlib.import_module(f"reservations.migrations.{_LEAF}")


def _migrate(target: str) -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([(_APP, target)])
    # Drop the cached project state so a later call re-reads the schema it just
    # changed.
    executor.loader.build_graph()


def _historical_state() -> ProjectState:
    """Project state just before 0035 runs.

    Pins ``reservations`` at 0034 (the ``Guest`` table + ``guest`` FKs that 0035
    drops are still present) but every OTHER app — notably ``accounts`` — at its
    LIVE leaf, so the projected ``accounts.Person`` matches the real DB schema.
    Using 0035's own frozen dependency set would resurrect columns since dropped
    downstream (GAP-046 removed ``Person.company`` in accounts 0012), and the
    historical INSERT would then fail against the live, company-less table.
    ``accounts`` sits below ``reservations`` on the import/migration spine, so
    pinning it forward while ``reservations`` stays at 0034 is consistent.

    A leaf of an app *above* reservations on the spine may FK into a reservations
    model created after 0034 (e.g. ``payments.SecurityDeposit.damage_claim`` →
    ``reservations.DamageClaim`` in 0037, BUG-008); including such a leaf as a
    target would drag reservations forward past the 0035 Guest drop and the
    historical ``Guest`` model would vanish. Exclude any other-app leaf whose
    forwards-plan requires a reservations migration newer than 0034.
    """
    loader = MigrationExecutor(connection).loader
    before = (_APP, _BEFORE)
    # reservations nodes strictly after 0034 (the 0035 branches, the 0036 merge,
    # 0037, …) — a target whose plan touches any of these moves reservations on.
    res_after_before = {n for n in loader.graph.nodes if n[0] == _APP} - set(
        loader.graph.forwards_plan(before)
    )
    targets = [before] + [
        leaf
        for leaf in loader.graph.leaf_nodes()
        if leaf[0] != _APP and not res_after_before.intersection(loader.graph.forwards_plan(leaf))
    ]
    return loader.project_state(targets)


def _rekey() -> None:
    """Run the migration's re-key against the live (0034) schema."""
    state = _historical_state()
    _migration._rekey_forward(state.apps, connection.schema_editor())


def _make_guest(HGuest: Any, **kwargs: object) -> Any:
    """Create a minimal historical Guest.

    Historical models have no custom ``save`` (no email-normalise), so the
    ``guest_active_contactable`` CHECK applies as written: an ACTIVE guest must
    carry an email or a phone. Default status is ACTIVE, so we always supply an
    email unless the caller overrides it.
    """
    defaults: dict[str, object] = {
        "first_name": "Test",
        "last_name": "Guest",
        "email": "g@example.com",
    }
    defaults.update(kwargs)
    return HGuest.objects.create(**defaults)


def _make_person(HPerson: Any, *, legacy_id: str | None, name: str) -> Any:
    """Create a minimal historical mirror Person.

    ``kind`` has a Python-level default but historical ``.save()`` does not
    reliably apply it across the projected state here, so set it explicitly —
    mirror Persons are customers (PersonKind.CUSTOMER == "customer").
    """
    return HPerson.objects.create(
        first_name=name,
        last_name="Person",
        kind="customer",
        legacy_id=legacy_id,
    )


def _delete_rows(table: str, pks: list[int]) -> None:
    """Hard-delete the given rows by pk with raw SQL.

    Bypasses the ORM cascade collector on purpose: the projected ``properties``
    state still references columns (e.g. ``groupfinance.security_deposit_*``)
    the live leaf schema has since dropped, so ``QuerySet.delete()`` would emit
    a SELECT against a non-existent column. None of the rows we create here have
    dependants, so a direct DELETE is safe.
    """
    if not pks:
        return
    placeholders = ", ".join(["%s"] * len(pks))
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", pks)


@pytest.mark.django_db(transaction=True)
def test_normal_rekey_uses_guest_legacy_id() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HGuest: Any = state.apps.get_model(_APP, "Guest")
    HPerson: Any = state.apps.get_model("accounts", "Person")
    guest_pks: list[int] = []
    person_pks: list[int] = []
    try:
        guest = _make_guest(HGuest, legacy_id="500")
        guest_pks.append(guest.pk)
        person = _make_person(HPerson, legacy_id=f"guest-{guest.pk}", name="Mirror")
        person_pks.append(person.pk)

        _rekey()

        person.refresh_from_db()
        assert person.legacy_id == "client-500"
    finally:
        _delete_rows("accounts_person", person_pks)
        _delete_rows("reservations_guest", guest_pks)
        _migrate(_LEAF)


@pytest.mark.django_db(transaction=True)
def test_null_source_rekeys_to_none_not_literal() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HGuest: Any = state.apps.get_model(_APP, "Guest")
    HPerson: Any = state.apps.get_model("accounts", "Person")
    guest_pks: list[int] = []
    person_pks: list[int] = []
    try:
        # (a) Guest exists but has a NULL legacy_id.
        guest = _make_guest(HGuest, legacy_id=None)
        guest_pks.append(guest.pk)
        p_null = _make_person(HPerson, legacy_id=f"guest-{guest.pk}", name="NullSrc")
        person_pks.append(p_null.pk)

        # (b) No matching Guest row at all (pk that does not exist).
        missing_pk = guest.pk + 9999
        p_missing = _make_person(HPerson, legacy_id=f"guest-{missing_pk}", name="NoGuest")
        person_pks.append(p_missing.pk)

        _rekey()

        p_null.refresh_from_db()
        p_missing.refresh_from_db()
        assert p_null.legacy_id is None
        assert p_missing.legacy_id is None
        # Never the literal "client-None".
        assert not HPerson.objects.filter(legacy_id="client-None").exists()
    finally:
        _delete_rows("accounts_person", person_pks)
        _delete_rows("reservations_guest", guest_pks)
        _migrate(_LEAF)


@pytest.mark.django_db(transaction=True)
def test_malformed_key_left_untouched() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HPerson: Any = state.apps.get_model("accounts", "Person")
    person_pks: list[int] = []
    try:
        person = _make_person(HPerson, legacy_id="guest-abc", name="Malformed")
        person_pks.append(person.pk)

        _rekey()

        person.refresh_from_db()
        assert person.legacy_id == "guest-abc"
    finally:
        _delete_rows("accounts_person", person_pks)
        _migrate(_LEAF)


@pytest.mark.django_db(transaction=True)
def test_rekey_is_idempotent() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HGuest: Any = state.apps.get_model(_APP, "Guest")
    HPerson: Any = state.apps.get_model("accounts", "Person")
    guest_pks: list[int] = []
    person_pks: list[int] = []
    try:
        guest = _make_guest(HGuest, legacy_id="500")
        guest_pks.append(guest.pk)
        person = _make_person(HPerson, legacy_id=f"guest-{guest.pk}", name="Mirror")
        person_pks.append(person.pk)

        _rekey()
        person.refresh_from_db()
        assert person.legacy_id == "client-500"

        # Second run: no guest- rows remain, so nothing changes.
        _rekey()
        person.refresh_from_db()
        assert person.legacy_id == "client-500"
        assert not HPerson.objects.filter(legacy_id__startswith="guest-").exists()
    finally:
        _delete_rows("accounts_person", person_pks)
        _delete_rows("reservations_guest", guest_pks)
        _migrate(_LEAF)


@pytest.mark.django_db(transaction=True)
def test_collision_fails_closed() -> None:
    _migrate(_BEFORE)
    state = _historical_state()
    HGuest: Any = state.apps.get_model(_APP, "Guest")
    HPerson: Any = state.apps.get_model("accounts", "Person")
    guest_pks: list[int] = []
    person_pks: list[int] = []
    try:
        # Two Guests share the same legacy_id "500" → both mirrors want
        # client-500. The second re-key finds client-500 already on another
        # Person and must fail closed.
        guest_a = _make_guest(HGuest, legacy_id="500")
        guest_b = _make_guest(HGuest, legacy_id="500")
        guest_pks.extend([guest_a.pk, guest_b.pk])
        p_a = _make_person(HPerson, legacy_id=f"guest-{guest_a.pk}", name="MirrorA")
        p_b = _make_person(HPerson, legacy_id=f"guest-{guest_b.pk}", name="MirrorB")
        person_pks.extend([p_a.pk, p_b.pk])

        with pytest.raises(RuntimeError):
            _rekey()
    finally:
        _delete_rows("accounts_person", person_pks)
        _delete_rows("reservations_guest", guest_pks)
        _migrate(_LEAF)
