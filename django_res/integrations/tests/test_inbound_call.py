"""IntegrationInboundCall — append-only idempotency ledger for inbound calls.

Design: 08-integrations.md §Idempotency, amended to store the full
`response_body` (a hash alone cannot replay a response — recorded erratum).
"""

from __future__ import annotations

import hashlib
import json

import pytest
from django.db.utils import IntegrityError

from integrations.enums import SyncProvider
from integrations.models import IntegrationInboundCall
from integrations.services.inbound import record_or_replay

pytestmark = pytest.mark.django_db


def _produce_201() -> tuple[int, dict[str, str]]:
    return 201, {"reference": "E123"}


def test_first_call_runs_produce_and_records_the_response() -> None:
    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key="k1",
        produce=_produce_201,
    )

    assert replayed is False
    assert call.response_status == 201
    assert call.response_body == {"reference": "E123"}
    expected_hash = hashlib.sha256(
        json.dumps({"reference": "E123"}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert call.response_body_hash == expected_hash
    assert IntegrationInboundCall.objects.count() == 1


def test_replay_returns_the_recorded_response_without_rerunning_produce() -> None:
    record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_produce_201
    )

    def _explodes() -> tuple[int, dict[str, str]]:
        raise AssertionError("produce must not run on replay")

    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_explodes
    )

    assert replayed is True
    assert call.response_status == 201
    assert call.response_body == {"reference": "E123"}
    assert IntegrationInboundCall.objects.count() == 1


def test_distinct_keys_are_processed_independently() -> None:
    record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_produce_201
    )
    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key="k2",
        produce=lambda: (200, {"reference": "E456"}),
    )

    assert replayed is False
    assert call.response_body == {"reference": "E456"}
    assert IntegrationInboundCall.objects.count() == 2


def test_produce_failure_records_nothing_so_a_retry_reprocesses() -> None:
    def _fails() -> tuple[int, dict[str, str]]:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        record_or_replay(provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_fails)

    assert IntegrationInboundCall.objects.count() == 0

    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_produce_201
    )
    assert replayed is False
    assert call.response_status == 201


def _blind_first_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make record_or_replay's pre-check miss once, simulating a lost race.

    A real race needs a second connection; blinding the first `.filter()` while
    a committed winner row exists drives the same code path deterministically:
    produce runs, the insert hits the unique constraint, the handler replays.
    """
    from integrations.services import inbound

    real_filter = IntegrationInboundCall.objects.filter
    calls = {"n": 0}

    def filter_blind_once(**kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            return IntegrationInboundCall.objects.none()
        return real_filter(**kwargs)

    monkeypatch.setattr(inbound.IntegrationInboundCall.objects, "filter", filter_blind_once)


def test_lost_concurrent_race_replays_the_winners_row(monkeypatch: pytest.MonkeyPatch) -> None:
    winner = IntegrationInboundCall.objects.create(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key="k1",
        response_status=201,
        response_body={"reference": "E-winner"},
        response_body_hash="",
    )
    _blind_first_lookup(monkeypatch)
    produced = {"ran": False}

    def _produce() -> tuple[int, dict[str, str]]:
        produced["ran"] = True
        return 201, {"reference": "E-loser"}

    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_produce
    )

    assert produced["ran"] is True  # the loser did the work, then rolled back
    assert replayed is True
    assert call.pk == winner.pk
    assert call.response_body == {"reference": "E-winner"}
    assert IntegrationInboundCall.objects.count() == 1


def test_unrelated_integrity_error_from_produce_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Even with a committed row for the same key, an IntegrityError raised by
    # produce itself (a different constraint) must never read as a replay.
    IntegrationInboundCall.objects.create(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key="k1",
        response_status=201,
        response_body={},
        response_body_hash="",
    )
    _blind_first_lookup(monkeypatch)

    def _produce() -> tuple[int, dict[str, str]]:
        raise IntegrityError('violates foreign key constraint "some_other_constraint"')

    with pytest.raises(IntegrityError, match="some_other_constraint"):
        record_or_replay(
            provider=SyncProvider.WORDPRESS_SITE, idempotency_key="k1", produce=_produce
        )


def test_duplicate_key_insert_is_rejected_at_the_db_level() -> None:
    IntegrationInboundCall.objects.create(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key="k1",
        response_status=201,
        response_body={},
        response_body_hash="",
    )
    with pytest.raises(IntegrityError):
        IntegrationInboundCall.objects.create(
            provider=SyncProvider.WORDPRESS_SITE,
            idempotency_key="k1",
            response_status=200,
            response_body={},
            response_body_hash="",
        )
