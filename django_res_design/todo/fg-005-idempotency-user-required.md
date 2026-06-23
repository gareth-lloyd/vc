> **⚠️ RE-SCOPED (2026-06-20, per `CRITIQUE-2026-06-19.md`)** — The premise below
> is moot as written: `IdempotencyRecord` is a **dead table** — zero runtime
> writers (`grep IdempotencyRecord.objects` → only the class def). Live
> idempotency is done entirely by `core/idempotency.py` meta-key stamping on
> per-model `meta` JSON (used by `payments/services/refund.py`,
> `manual_payment.py`), and `done/FG-010` shipped DB backstops there instead. So
> the `user`-required FK blocks nothing today.
>
> **DECISION (2026-06-23): delete the dead table.** Live dedupe is the
> `core/idempotency.py` meta-key path; `IdempotencyRecord` has zero runtime
> writers (`grep IdempotencyRecord.objects` → only the class def + migration).
> The nullable-FK redesign below is therefore moot — **do not implement it.**
> Remaining work is removal, not repair:
>
> - Drop the `IdempotencyRecord` model (`core/models/idempotency.py`) + its
>   `core/models/__init__.py` export, with a `core/` migration to drop the table.
> - Confirm nothing imports it (only migrations should reference it after).
> - Acceptance becomes: table gone, `lint-imports`/tests green, no behaviour
>   change (live dedupe already lives in `core/idempotency.py`).
>
> _Original (revive-path) ticket preserved below for context only._

# FG-005 — `IdempotencyRecord.user` is required; system actors can't dedupe

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F5
- **Files:** `core/models/idempotency.py:22–26`

## Problem

```python
user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
```

Unique key is `(user, path, key)`. System actors (`actor=None` per the
service-layer convention) can't write an idempotency record. Webhook
retries — the canonical use case — don't have a user. Today this is
worked around at the call-site (provider-reference uniqueness on
Payment), but the design says "use this table" and the schema says "you
can't".

## Proposed fix

Make `user` nullable and switch the unique key:

```python
user = models.ForeignKey(..., on_delete=PROTECT, null=True, blank=True)

constraints = [
    UniqueConstraint(
        fields=["user", "path", "key"],
        name="idempotency_unique_user_path_key",
        condition=Q(user__isnull=False),
    ),
    UniqueConstraint(
        fields=["path", "key"],
        name="idempotency_unique_system_path_key",
        condition=Q(user__isnull=True),
    ),
]
```

Add a `scope` column if disambiguating system vs webhook callers turns
out to matter at read time.

## Acceptance

- `IdempotencyRecord.objects.create(user=None, path=..., key=...)`
  succeeds and dedupes a second call with the same `(path, key)`.
- Existing user-keyed paths still dedupe per-user.
- Migration handles existing rows (today they all have a user; no
  backfill needed).

## Dependencies

Coordinate with the Flywire webhook handler — that's the natural first
caller of the new system-actor dedupe path.
