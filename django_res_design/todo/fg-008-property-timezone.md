# FG-008 — `PropertySettings.check_in_time` / `check_out_time` have no timezone

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F8
- **Files:** `properties/models/settings.py:59–60`,
  `properties/models/property.py` (add `timezone`)

## Problem

`TimeField` is naive. `Property` has no `timezone` column. Two villas in
different timezones with `check_in_time='16:00'` are indistinguishable
in the schema. Reminder-emails ("how many hours until check-in"), pricing
changeover, and availability windows can't compute wall-clock locally.

## Proposed fix

Add `Property.timezone = models.CharField(max_length=64, choices=…)`
(IANA names) with a sensible default (probably `"Europe/London"` for the
current portfolio). Treat `check_in_time` / `check_out_time` as
wall-clock-in-that-timezone wherever they are consumed (services,
comms compilers, ICS feeds).

Backfill: default every existing property to the company's primary
timezone, then surface in the admin / property-settings UI for ops to
correct outliers.

## Acceptance

- `Property.timezone` field with IANA names (use `zoneinfo` to validate).
- Migration sets a default for existing rows.
- Service layer converts `check_in_time` + booking date to a tz-aware
  `datetime` consistently.
- Test fixtures updated to set a non-default timezone where relevant.

## Dependencies

Comms reminder templates depend on this — they're a downstream consumer
of "hours until check-in". Worth lining up with [Q-005](#) (currency
display normalisation) since both touch site-level locale data.
