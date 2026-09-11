# Q-028 — Legacy-loader questions for Nick (the ones the audit could not settle from the data)

- **Severity:** Question (each blocks one small slice of loader work; none
  blocks cutover on its own).
- **Source:** 2026-09-11 legacy-loader audit. Everything the audit *could*
  decide from the dump or the legacy code was decided the same day (recorded
  in BUG-028 / BUG-029 / BUG-030 / GAP-108 / GAP-109 and to be written into
  `design/decisions.md` as they land). The residue below needs the owner.
- **Files:** `django_res/data_migration/management/commands/import_past_bookers.py:206-256`;
  `django_res/data_migration/loaders/properties.py` (concierge tier);
  `django_res/data_migration/loaders/property_children.py:83-164`
  (`GallaryOrder`); `django_res/data_migration/loaders/pricing.py:534-543`
  (extras — GAP-107 §1).
- **Format:** numbered, each with a suggested answer so a one-word reply per
  number is complete, in the style of
  [owner-questions-2026-07-02.md](owner-questions-2026-07-02.md). Fold onto
  the next Nick call rather than sending as a standalone e-mail.

## Questions

1. **Future stays in the Past Bookers sheet.** The Booking History sheet has
   141 stays dated 2026 and 17 dated 2027 (plus 160 for 2025). Today they
   import as "past stays" and make those guests count as repeat customers
   before they have stayed. **Suggested answer:** skip anything dated after
   the cutover year and list them in the import report; they are bookings-to-
   be and will arrive through the normal booking flow. *(Alternative: keep
   them all — a stay is a relationship fact regardless of date.)*

2. **Concierge tier per villa.** Legacy stores a concierge service tier on
   291 live villas (tier 1 ×165, tier 2 ×126). The new system has no field
   for it and concierge is deferred to M2. **Suggested answer:** keep the
   number on the villa as a plain "concierge tier" field now (cheap, nothing
   reads it yet) rather than lose it and re-derive from the archived dump
   later. *(Alternative: drop it; we have the dump.)*

3. **Featured-image grid slots.** Legacy's image screen lets a curator pin
   up to four images into a "featured grid" (696 images carry a slot 1–4).
   The new gallery has a hero and a sort order, no slots. **Suggested
   answer:** ask Ben whether the rebuilt website (GAP-106) wants a featured
   grid; if yes we carry the slot across, if no we drop it and record the
   count. *(Depends on Q-026 / GAP-106.)*

4. **Legacy extras catalogue** (GAP-107 §1, already open — restated here so
   it rides the same call). 137 live per-villa extras (chef, pool heating,
   …) live in the legacy rate table and are not loaded, so every migrated
   villa starts with an empty extras list and the Zoho villa payload's
   `extras[]` is empty. **Suggested answer:** port them into the new per-villa
   extras with their date windows. *(Alternative: drop and re-enter by hand
   post-cutover.)*

## Disposition

Record each answer in `design/decisions.md` and on the owning ticket
(1 → BUG-030 §36; 2, 3 → GAP-109 rows 10/11; 4 → GAP-107 §1); retire this
file to `reviews/` when all four are answered.
