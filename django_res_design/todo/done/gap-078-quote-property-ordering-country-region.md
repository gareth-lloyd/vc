> **✅ RESOLVED (2026-07-12)** — shipped on `feat/gap-078` (units 1–4).
> Picker: `/properties` list rows carry `region_name`/`country_name`, the
> quote builder requests `ordering=region__country__name,region__name,name,id`
> (trailing `id` keeps paging stable), and `QuoteResultsList` renders country
> sections / region sub-groups with disambiguating headers only (≥2 rule),
> geo-less rows under "Other locations", group structure always mounted so
> Load-more never remounts cards. Email + operator preview: lines ordered
> country → region → name, `line_groups` + "Country · Region" header rows in
> BOTH `quotation.sent.body.mjml` (comms 0003 re-sync migration) and
> `quotation_quote.html`; single-group renders header-less.
> **Deferred:** the weekly-vs-nightly section break — GAP-074/075 are unbuilt
> and product-gated (Debbie call); a pointer note now sits in GAP-074 so the
> break lands with the nightly work.

# GAP-078 — Quote property ordering: group by country/region + weekly-vs-nightly section break

- **Severity:** 🟢 Gap (quote builder + guest email presentation). FE-led plus a
  small backend `ordering` addition.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: villas in the
  picker come up alphabetically / "in a completely random order"; wants them
  **bunched by country then region**, with subtitles/section headers ("that's how
  I do it — filter by country"). In the quote email he also wants weekly-block
  properties first, then a **section break** for the flexible/nightly-priced
  properties, omitting any empty section.
- **Files touched (best-guess):**
  - Picker order: `frontend/src/features/quotations/api.ts` —
    `fetchCandidateProperties` (~L152-188) sends **no `ordering`**, so results
    fall to `Property.Meta.ordering = ["name", "id"]`
    (`django_res/properties/models/property.py` ~L99-103); the viewset
    `ordering_fields` (`django_res/properties/views/property.py` ~L69-72) exposes
    only `name/display_name/created_at/updated_at` — **no country/region**.
    Country/region exist only as *filter* dropdowns.
  - Picker render: `QuoteResultsList.tsx` — partitions available / manual /
    unavailable, never reorders by geography (its own comment notes "pagination
    is over name-sorted candidates").
  - Email order: `build_quotation_context` iterates `quotation.lines.real()` in
    `QuotationLine.Meta.ordering = ["pk"]` (**insertion**) order
    (`django_res/reservations/services/quotation_render.py` ~L96-103,
    `quotation.py` ~L274); template
    `django_res/comms/templates/comms/quotation.sent.body.mjml`
    `{% for line in lines %}` (no headers, no section break).

## Problem

No country/region grouping or sort anywhere in the picker; the quote email
renders lines in insertion order with no headers and no weekly-vs-nightly
separation.

## Proposed fix

- **Backend:** add `region` / `country` to the Property viewset
  `ordering_fields`; have the candidate query request country → region → name
  ordering (or sort client-side).
- **Picker:** group results under country/region subheadings in
  `QuoteResultsList` (keep the available/manual/unavailable partition *within*
  each group).
- **Email:** order lines country → region and insert section headers; add a
  weekly-block vs nightly/flexible section break (the nightly section is
  populated by GAP-074/075); omit any empty section. Likely needs a per-line
  "pricing style" flag on the render context to partition.

## Acceptance

- Picker results are grouped and labelled by country then region. (component test)
- The quote email groups properties by country/region and shows a weekly-vs-
  nightly section break, omitting empty sections. (render test)
- Quality gate green both stacks.

## Dependencies

- The weekly-vs-nightly section needs **GAP-074 / GAP-075** (nightly options must
  exist).
- Related **GAP-005** (quotation flow/spine UX), **GAP-013** (builder UX polish),
  **GAP-080** (currency-obviousness — currency tracks country, so grouping helps).
