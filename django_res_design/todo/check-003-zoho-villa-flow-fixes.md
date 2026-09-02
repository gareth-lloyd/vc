# CHECK-003 — Zoho villa flow: fixes raised with Limitless

- **Severity:** 🔎 Check (external party — closed by verifying someone
  else's change, not by building).
- **Owner of the work:** Limitless (Zoho Flow `limitless_upsert_villa`).
  Not in this repo.
- **Raised:** 2026-09-01, by email, off the villa-sync demo transcript +
  the Deluge upsert function.
- **Verify with:** `manage.py zoho_send_sample` against the Limitless
  sandbox, then read the resulting Products.

## Why this is a check, not a gap

Our payload (`django_res/properties/services/zoho_payload.py`,
`build_property_payload`) already carries everything below. Two items from
this review are ours and are filed separately — **GAP-096** (Organisation has
no push of its own) and the relative hero-image URL, which is a note on
**GAP-012** — and are excluded here.

## Items to verify

1. **`features[]` is dropped entirely.** Nothing in the function references
   it; the comma-separated list in the demo is the per-room `attributes`,
   which is a different thing. The villa's own feature list — including the
   GAP-067 derived ones — never reaches the CRM, and it is the most useful
   segmentation axis on a Product. Each entry carries `name`, `slug`,
   `category`, `service_type`, `is_derived`.

2. **The management company picked can be the wrong one.** `contacts[]` is
   ordered by role then pk (`properties/services/zoho_payload.py:214`), so
   the *first* `management_company` row is the oldest. The loop takes that
   first match and ignores both `end_date` and `is_primary`, so an ended
   assignment beats the current one. Asked for: skip rows with a past
   `end_date`, prefer `is_primary`.
   - *Verify:* a villa whose management company has been replaced.

3. **The rooms subform looks like it re-creates rows.** The demo's "six
   rooms numbered from seven" is the usual signature. Villas re-push often —
   every child save *and delete* bumps the parent (`properties/signals.py:99`
   covers features, contact assignments, location, capacity, rooms, images,
   beds, room attributes), so anything that appends compounds fast. Two
   specifics: Zoho matches subform rows on its own row `id`, not our
   `RES_ID`; and `if(rooms_subform.size() > 0)` omits the key when the list
   is empty, so deleting the last room leaves the old subform intact.
   - *Verify:* push the same villa twice and count rows; then delete a room
     and push again.

4. **Three functions read the create response three different ways.**
   Contacts uses `.get("data").get(0).get("details").get("id")`, enquiry uses
   `.get("id")`, villa uses `.get("id")` for both Accounts and Products. At
   most one is right; here it would null `management_company_id` (which sets
   the `Management_Company` lookup) and `product_id` on first create. Asked
   for: settle it once, same form in all three.

5. **Underscored enum values reach the CRM raw.** `subText(0,1).toUpperCase()`
   capitalises the first letter only, so `lower_ground` → "Lower_ground" and
   `third_plus` → "Third_plus"; bed sizes aren't capitalised at all, so
   `super_king` renders as `"1 super_king double"`. The three test villas
   would only have hit `ground`/`first`, which is why it looked clean. Asked
   for: map to display labels (`properties/enums.py` — `RoomFloor`,
   `BedSize`, `EnsuiteType`; note `both` reads "Bath & shower", not "Both").
   - *Verify:* a villa with a lower-ground room and a super-king bed.

6. **Region should come from the structured field.** Their comment picks
   `location` as the sole source to stop two sources disagreeing, but
   `locality_region` is a free-text `CharField(128)` while `region` is the FK
   we group and report on everywhere else. Asked for: `Region` ←
   `region.name`, `Country` ← `region.country.name`, keeping
   `locality_town`/`locality_region` as separate locality fields. Also asked
   them to flag any record where `location.country` and `region.country`
   disagree — that would be a data problem at our end.

7. **Status collapses to a boolean.** `draft`/`active`/`archived` →
   `Product_Active`, so draft and archived are indistinguishable. Asked for:
   send `status` as text too. Open question back to them: should a draft
   villa create a Product at all, or do we hold those back?

8. **Unmapped fields needing a decision.** `address_line_3`, `latitude`/
   `longitude` (the legacy Zoho villa record carried Co-ordinates — dropping
   them is a step backwards), `timezone`, `channel`, `licence_number`,
   `video_url`, and on rooms `placement`, `placement_note`, `access`,
   `sort_order`. The significant one is the **owner contact**: legacy carried
   Owner and we send `contacts[role=owner]`. Their comment says other roles
   are out of scope "per earlier decision" — we have asked for a pointer to
   that decision, because it reads as a regression against legacy.

9. **`RES_Source_JSON` puts contact PII on a Product.** `contacts[].person`
   carries `primary_email`/`primary_phone` for owners and managers, so the
   raw snapshot lands personal details in a text field on a Products record,
   which has different visibility rules to Contacts. Asked: check who can see
   Products before this leaves the sandbox.

10. **Search-response guard.** `products.get("data").size()` assumes `data`
    is present; if the v8 search returns 204 with no body on an empty result,
    that line throws. Their three test villas were presumably all creates, so
    this is a question rather than a confirmed defect — the same pattern is
    used for the Accounts search.

## Do not build

**`Property_Category`.** We have an open decision to remove
`Property.category` entirely (**GAP-093** — country + region is enough), so
building out that picklist is wasted effort on both sides. Confirm to
Limitless when GAP-093 lands.

## Acceptance

- Each numbered item confirmed against the sandbox by push-and-read.
- The owner-contact scope question answered, with the earlier decision
  produced or the scope reopened.
- The test batch we asked for has been run: a villa with features; one whose
  management company has been replaced; one with a lower-ground room and a
  super-king bed; one where a room has since been deleted; and the same villa
  pushed twice to settle the subform behaviour.

## Dependencies

- **GAP-096** — Organisation push kind. Item 2 only fixes *which* Account is
  linked; Accounts still come into being as a side effect of a villa push
  until GAP-096 lands.
- **GAP-093** — remove `Property.category`; see "Do not build" above.
- **GAP-012** — hero-image URL is relative until S3 hosting lands; the text
  field Limitless chose is the right call in the meantime.
- **GAP-097** — "verified" means a human read the Product record.
