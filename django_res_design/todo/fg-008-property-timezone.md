# FG-008 — `PropertySettings.check_in_time` / `check_out_time` have no timezone

- **Severity:** 🟠 Footgun
- **Status:** ✅ **resolved**
- **Source:** the 2026-05-26 data-model deep audit §F8
- **Files:** `properties/models/settings.py:59–60`,
  `properties/models/property.py` (add `timezone`)

## Resolution (what actually shipped)

The footgun is closed. Implementation **deviated from the proposed fix** — for
the better — so it's worth recording the shape:

- The field landed on **`PropertyLocation.timezone`**, not `Property.timezone`.
  Timezone is a geographic fact of the *place* (it follows `country`), not a
  policy of the property abstract — so it lives beside `country` on the
  location row. See the rationale in `properties/timezones.py`.
- `properties/timezones.py` — `validate_iana_timezone` (zoneinfo-backed),
  `COUNTRY_TIMEZONES` map + `representative_timezone()`. `tzdata` is an
  unconditional dependency so `ZoneInfo` resolves on the slim deploy image.
- Migration `0013_propertylocation_timezone` adds the field and backfills from
  country; unmapped countries keep the honest `UTC` default.
- **Service seam** `properties/services/timing.py` —
  `local_check_in_datetime` / `local_check_out_datetime` combine a booking
  date + effective check-in/out time + location timezone into a tz-aware
  datetime, tolerant by design. Tested in `tests/test_timing.py` (includes the
  "same wall-clock, two zones" footgun case).
- Factory + legacy loader set the zone from the country; fixtures exercise a
  non-default zone.
- **REST + frontend surface** (this branch): `timezone` is exposed and editable
  through `/properties/{id}/settings` (`PropertySettingsSerializer` bridges to
  `property.location.timezone`) and the property Settings tab, beside the
  check-in/out times it contextualises. Previously it was editable only via
  Django admin.

Two audit-implied "consumer gaps" turned out to be non-issues: the changeover
comparison in `reservations/services/availability.py` is **intra-property**
(both times share one zone), and no comms context yet computes
"hours until check-in" — the seam is ready for when reminder templates need it.

## Original ticket (for the record)

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
