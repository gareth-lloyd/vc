# GAP-094 — House rules must flow into the booking contract

- **Severity:** 🟢 Gap (requirement capture — deferred until the booking
  contract exists). No code change today.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[02:08–02:35]`, recap `[04:09–04:15]`.
- **Files touched (best-guess, when built):**
  - `django_res/properties/enums.py:104` — `DescriptionSection.HOUSE_RULES`
    (the source content; keep it through the GAP-090 enum rewrite).
  - `django_res/data_migration/loaders/properties.py:235–236` — legacy
    `HouseRules` → `HOUSE_RULES`, already imported.
  - Booking-contract generation — **does not exist yet**; no
    `booking_contract` / rental-agreement / terms module in the codebase.

## Problem

House rules are already modelled and imported, and Nick confirms the field
itself is right — *"house rules is good"*. The requirement is about where the
content goes, and it isn't satisfied anywhere:

> *"This is not to be shown online, but this will come into effect during the
> booking process, and the booking system will effectively pull the house
> rules through to form part of the booking contract."* `[02:18]`

Two constraints fall out, and both are easy to lose:

1. **Never rendered publicly.** House rules must not leak into the villa page
   or the WordPress payload. Note the adjacent design in GAP-091: content that
   *could* belong in house rules but should be public goes in the "other
   information" free text instead — so the split is deliberate and the two
   fields are not interchangeable.
2. **Snapshot at booking, not a live reference.** A contract that renders
   today's house rules would silently rewrite what a guest agreed to when the
   property's rules are later edited. The contract needs the rules **as they
   stood when the booking was confirmed**.

Filed now purely so the requirement survives to the booking-contract work —
this is not actionable until that surface exists.

## Proposed fix

When the booking contract is built:

- Pull `HOUSE_RULES` for the booked property into the contract document.
- **Snapshot the text onto the booking** at confirmation rather than
  referencing the live section, so later property edits can't retroactively
  change an agreed contract.
- Keep house rules out of every public/WP payload — assert it, don't assume
  it.

## Acceptance

- Booking contract renders the property's house rules. (test)
- The rendered text is the snapshot taken at confirmation; editing the
  property's house rules afterwards does not change an existing booking's
  contract. (test)
- House rules appear in no public serializer or WordPress payload. (test)

## Dependencies

- **Blocked on the booking contract / guest-facing document surface**, which
  doesn't exist. Related deferred guest-facing work: GAP-051 (checkout charge
  itemisation, *"deferred until the guest checkout page exists"*).
- **GAP-090** — keep `house_rules` when the `DescriptionSection` enum is
  rebuilt.
- **GAP-091** — the public counterpart; the "other information" free text is
  where house-rules-adjacent content goes when it *should* be shown.
