# SMELL-005 — Verify no residual `Property.country` free-text field

- **Status:** ❌ **DROPPED** (2026-05-27 critique) — verified clean.
  `rg "country = models\." django_res/properties/` returns only
  `Location.country` and `geo.country`, both FKs to `Country`. No
  free-text `country` on `Property`. The CLAUDE.md note refers to a
  Canary-project convention, not this codebase.
- **Severity:** 🟡 Smell / verification
- **Source:** the 2026-05-26 data-model deep audit §S5
- **Files:** `properties/models/property.py`, `properties/migrations/*`

## Problem

`~/.claude/CLAUDE.md` and the project CLAUDE.md both say
"use `hotel.country_code` with `get_country()`, not `hotel.country`
(free-text string)". The rule's existence implies the free-text field
either lived in the legacy schema or still lurks somewhere. The audit
didn't find one on `Property`, but didn't grep exhaustively either.

## Proposed fix

`rg -n "country = models\." django_res/properties/` and confirm only
`country_code = CharField(...)` exists. If a free-text `country` field
turns up, schedule its removal:

1. Make non-required.
2. Backfill `country_code` from it where possible.
3. Drop the column in a follow-up migration.

## Dependencies

None — pure verification work, drop the ticket if grep is clean.
