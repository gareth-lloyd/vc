# GAP-054 — Damage-claims workflow remainder (thresholds, guest email, capture-guard)

- **Severity:** 🟢 Gap (designed-but-unbuilt surface area)
- **Source:** `product-design/03-workflows.md` flow 8 (SD capture / damages),
  lines 420–447; continuation of `done/bug-008-securitydeposit-damageclaim-fk.md`
  ("damages workflow … deferred to wf 8/17").
- **Files:** `reservations/services/damage_claims.py`,
  `payments/services/security_deposit.py`,
  `reservations/models/damage_claim.py` (`accepted_by_guest_at`),
  `core/enums.py` (`StaffRole`), `comms/` (email templates),
  `frontend/src/features/bookings/components/DamageClaimsSection.tsx` /
  `DamageClaimPhotosDialog.tsx`.

## Context — what already shipped (wf8, merge `c20dc9e`, 2026-07-01)

The `/ship` "state machine + photos" landing built two of the deferred pieces:

- **Enforced approval state machine** — `DamageClaimService` transition map
  (OPEN→APPROVED→SETTLED/WITHDRAWN, SETTLED/WITHDRAWN terminal),
  `InvalidTransition`→409, closed-claim edit guard; `:approve` endpoint + FE
  row-action gating.
- **SETTLED auto-set by the SD capture** — `SecurityDepositService.claim()`
  settles the linked claim when it is OPEN/APPROVED (idempotent, row-locked).
  **`:settle` is deliberately NOT an operator endpoint** — settlement is the
  money-move's side effect. Do not re-add it.
- **Photo upload pipeline** — `DamageClaimPhoto` model (audited), nested
  upload/list/delete endpoints double-scoped by booking+claim (IDOR), FE
  `DamageClaimPhotosDialog`.

## Problem — what remains deferred

The damages flow is functional but the spec's permission and guest-facing
pieces are unbuilt. Today **any `RESERVATIONS` operator can file, approve, and
(via the accounts-gated SD `:claim`) capture any amount**, silently, with no
guest-facing artefact.

1. **Threshold permissions + `Senior Operator` role** (`03-workflows.md:447`):
   damages capture **> £500 requires Senior Op + photos**, **> £2000 requires
   Admin**; owner notification when damages **> threshold** (`:440`). No
   `Senior Operator` role exists in `StaffRole` yet — this is a cross-cutting
   addition (the same role gates price overrides, refunds-to-threshold, villa
   changes; see `03-workflows.md:19`), so scope it as its own unit or a shared
   `gap-*` if other flows need it first.
2. **Damages report → guest email + acceptance** (`03-workflows.md:429`): the
   report (description, itemised amount, **photos**, optional invoice/repair-quote
   attachments) is sent to the guest with the partial-refund/capture email, and
   is part of the audit log. `DamageClaim.accepted_by_guest_at` is a live column
   with **no flow that ever sets it** — either wire guest acceptance or note it
   as intentionally-inert. Needs a `comms/` template + a `booking.damages_claim`
   (or similarly named) email trigger on capture.
3. **Tighten `_resolve_damage_claim` on capture** (noted out-of-scope in the
   wf8 plan): capture currently accepts a linked claim in any non-foreign
   state; consider rejecting a claim that is already SETTLED/WITHDRAWN (vs the
   current no-op guard that just skips the settle). Low urgency — the settle
   step is already state-safe — but the *resolve* step is looser than the money
   move deserves.
4. **Photo polish** (all deferred in the wf8 plan): reordering, server-side
   thumbnailing / EXIF-strip / virus-scan, and the "optional invoice
   attachments (repair quote)" from `:429` (a second attachment kind beyond the
   evidence photo). None block the core flow.

## Proposed fix

Slice by dependency: (1) `Senior Operator` role is the gating prerequisite for
the threshold rules and likely shared with refunds/overrides — land it first
(or confirm it belongs in a dedicated auth ticket). (2) The guest email +
acceptance is a self-contained `comms/` unit. (3) and (4) are small,
touch-the-app-next hygiene items.

## Acceptance

- Capture > £500 without Senior Op (or without photos) is refused server-side;
  > £2000 requires Admin; tests cover each boundary.
- A damages capture sends the guest a report email (description + itemised
  amount + photo links); the send is audited.
- `accepted_by_guest_at` is either set by a real flow or explicitly documented
  as inert.
- `_resolve_damage_claim` decision (reject vs skip non-OPEN/withdrawn) made and
  tested.

## Dependencies

- Blocked-by / shares scope with the **`Senior Operator` role** (not yet in
  `StaffRole`) — also required by price-override, refund-threshold, and
  villa-change flows (`03-workflows.md:152/264/368`). Decide whether that role
  is its own ticket before starting the threshold unit.
- Builds on `done/bug-008-securitydeposit-damageclaim-fk.md` and the wf8
  state-machine/photos landing (`c20dc9e`).
