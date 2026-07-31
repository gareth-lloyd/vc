# GAP-088 — BookingChargeItem category taxonomy

> **✅ RESOLVED (2026-07-31)** — built as 3 TDD units on `feat/gap-088`.
> Decision (proposed-fix item 2): **superset**, not shared enum —
> `ChargeCategory` in `reservations/enums.py` embeds all 8 `ExtraKind`
> values verbatim (string+label equality pinned by test, so the vocabularies
> cannot drift) plus charge-only `damage`/`credit`. `category` column on
> `BookingChargeItem` (migration 0007, default/backfill `other` incl.
> GAP-017 legacy rows), read+write serializers (unknown values 400),
> `ChargeItemService.create()` kwarg + BookingEvent snapshot + AuditLog
> tracked fields. Zoho `extras[]` placeholders filled: snapshot extras pass
> their stored `ExtraKind` through **sanitized** (kind outside the
> vocabulary → null — manual-override snapshot writes are unfenced; a
> charge-only value like `damage` passes), charge lines send
> `item.category`; SNAPSHOT_EXTRAS fixture's fake kinds corrected to real
> values in the same commit as the assertion flips. FE: category
> `EnumSelect` above the free-text label in `ChargeItemFormDialog`
> (defaults "other"), `CHARGE_CATEGORIES` mirror + tolerant read schema
> (`.catch(undefined)` so a future backend value can't break the Finance
> tab), backend category 400s render inline, en+el labels (shared 8 copy
> the reviewed `extra_kind` Greek; 3 new strings manifest-tracked);
> `EnumSelect` lifted to `src/components/form/` (generic). No read-side
> category display (FinanceTab columns unchanged) — Zoho is the only
> consumer for now. Zoho-side dropdown config is Ben's half (2026-08-12
> call).

- **Severity:** 🟢 Gap (reporting consistency).
- **Source:** Limitless call 2026-07-29 — Ben's reporting-consistency ask:
  extras labels must be consistent between res and Zoho, so a
  **predetermined dropdown + free-text fallback**, not free text alone.
  Filed 2026-07-29.
- **Files:**
  - `django_res/reservations/models/charge_item.py` — `BookingChargeItem`
    has free-text `label` (~L25) + signed `amount` + `commissionable`
    (GAP-076) + `notes`. **No category column.**
  - `django_res/pricing/enums.py` — `ExtraKind` (~L25-35): the existing
    fixed vocabulary (`cleaning`, `pet_fee`, `heating`, `linen`,
    `extra_bed`, `service_fee`, `resort_fee`, `other`) used by pricing
    `Extra.kind` (`pricing/models/extra.py` ~L21).
  - `frontend/src/features/bookings/components/ChargeItemFormDialog.tsx` —
    the charge-item create/edit form (label + amount + commissionable +
    notes today).

## Problem

Manual booking charges are free-text-labelled, so the same real-world thing
lands in Zoho as "Cleaning", "cleaning fee", "final clean", … — useless for
CRM reporting. Pricing-side extras already carry a fixed `ExtraKind`, so the
two systems can't even be aligned res-internally, let alone with Zoho's
dropdown. GAP-085's itemized `extras[]` needs a stable `category` value per
entry; this ticket supplies it.

## Proposed fix

1. **`category` enum on `BookingChargeItem`** — values aligned with
   `ExtraKind`; keep the free-text `label` alongside for detail ("Cleaning
   — mid-stay extra clean"). Default/backfill existing rows (incl.
   legacy-imported GAP-017 rows) to `other`.
2. **Decide: share `ExtraKind` or define a superset.** Sharing is the
   spine-legal easy path (`reservations` may import from `pricing`), but
   charge items also cover credits/adjustments that aren't quote-time
   extras — if the call-agreed dropdown needs values `ExtraKind` lacks
   (e.g. "damage", "credit"), define a `ChargeCategory` superset that
   embeds the `ExtraKind` values verbatim (same strings, so Zoho sees ONE
   vocabulary). Do not fork the shared values' spellings.
3. **Migration** + serializer exposure (read + write, validated choice).
4. **FE dropdown** in `ChargeItemFormDialog` (category select + label text
   input = the "dropdown + free-text fallback" shape from the call), en+el.
5. **Zoho itemization** — include `category` in the GAP-085 `extras[]`
   entries (charge items send the enum value; snapshot extras already have
   `ExtraKind` via the pricing model).

## Acceptance

- Every charge item carries a category; API rejects unknown values; old
  rows read `other`.
- Form shows the dropdown; label stays free text.
- GAP-085 payload entries carry the enum value; pricing `Extra` and charge
  items present ONE consistent vocabulary to Zoho.
- Quality gates green (backend + frontend).

## Dependencies

- None hard. **GAP-085** consumes the enum (soft dependency in that
  direction). [GAP-076 ✅](done/gap-076-non-commissionable-extras.md) put
  `commissionable` on both models — same two-model alignment pattern.
