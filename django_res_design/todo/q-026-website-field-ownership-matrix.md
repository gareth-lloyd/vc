# Q-026 — Website contract questions for Mojo: which fields Res owns (and what happens to a site-side edit), and whether country/destination hub pages are Res-fed

> **Scope widened 2026-09-16 (todo consolidation):** absorbs **Q-027** (are
> country and destination hub pages Res-fed, or marketing pages Mojo owns?) —
> see §"Merged from Q-027" at the end. Both questions go to the same people
> (Ben Wood, Dave Thomas) and both set the scope of the GAP-106 payload, so
> they are one conversation. Answer the two independently: the field matrix
> blocks GAP-106 unit 1; the hub question decides whether `Country` needs a
> slug and `Region.slug` must go globally unique, and should be answered
> before GAP-096's `region` push kind (was GAP-103) is built.

- **Severity:** Question (blocks GAP-106 unit 1's field list on our side, and
  Mojo's collection modelling on theirs — both sides are guessing until this
  is written down).
- **Source:** Mojo website-rebuild thread 2026-09-09. Ben asked for Res to own
  *more* than proposed — meta titles, meta descriptions, and editorial lines
  such as "why we love it" — because *"a resync sometimes removes and
  recreates a page rather than updating it, and anything appended on the
  website side is lost."*
- **Files:** `django_res/properties/services/website_payload.py` (GAP-106
  unit 1, when built); `django_res/properties/models/descriptions.py`.
- **Decision needed from:** Gareth, Ben Wood (Mojo), Dave Thomas (SEO).

## Problem

Ben's stated reason is a **symptom of the current manual sync, not an argument
about ownership**. Under GAP-106 the push is an idempotent upsert keyed on
`RES_ID` that only writes the fields it owns — it never deletes and recreates
a page, so nothing appended site-side is lost. Deciding where content lives on
the basis of a failure mode we are removing is the wrong basis, and it would
land us with fields we then have to build editors and validation for.

But once that guarantee is stated, the question is still open on its merits,
and both sides need the answer before they build. Two authoring homes for
villa content is genuinely confusing for staff — Chloe is already entering
villa detail in Res per Nick's 2026-08-06 direction — so "keep it all in Res"
is not an unreasonable position, just one that has to be argued from the right
premise.

## The three-way split to settle

**Res owns** (uncontested): name, display name, slug, region + country,
capacity, rooms, beds, room attributes, features, other-information tags and
copy, description sections, images.

**Site owns** (uncontested): URL and path, page layout and block composition,
journal and guides, marketing collections, OG image selection.

**Contested — the actual decision:**

| Field | For Res owning | For the site owning |
|---|---|---|
| SEO meta title | one authoring home; populated for every villa automatically | Dave tunes these against search data; our system has no SERP preview, no length counters, no keyword context |
| SEO meta description | same | same |
| "Why we love it" / editorial line | sits naturally beside the villa record Chloe already edits | it is marketing voice, iterated with the page design |

## Proposed answer

**Res supplies a default; the site may override; the override always wins on
resync.** Ben gets a populated starting point for every villa rather than 275
empty meta fields, Dave keeps the field he actually tunes, and no push ever
stamps on a considered edit. Costs us one nullable field per item and costs
Mojo a per-field "overridden" flag.

If that is accepted, the rule generalises: **every field has exactly one
owner, and where both want one, Res defaults and the site overrides.**

## Acceptance

- A written matrix — field, owner, overridable yes/no — agreed by all three
  parties and committed alongside GAP-106 before unit 1's field list is
  frozen.
- GAP-106's payload test asserts the agreed list exactly, so drift from the
  matrix fails CI rather than being discovered on the site.

## Dependencies

- **Blocks GAP-106 unit 1** (final field list).
- The merged hub question (was Q-027) scopes the geo half of the GAP-106
  payload and GAP-096's `region` push kind (was GAP-103) — see its own
  Dependencies in §"Merged from Q-027".
- Related **GAP-090** / **GAP-092** — the description-section set is part of
  what Res owns here; settle those first or the matrix names a moving target.

---

## Merged from Q-027 — Are country and destination hub pages Res-fed, or marketing pages Mojo owns?

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [Q-027](done/q-027-are-country-destination-hubs-res-fed.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to Q-027 elsewhere now means this section._

- **Severity:** Question (decides whether `Country` needs a slug at all, and
  whether `Region` needs globally-unique ones — a schema question we should
  not answer by accident while building GAP-106).
- **Source:** URL-structure review of the live site, 2026-09-09 (Yoast
  sitemaps).
- **Files:** `django_res/properties/models/geo.py:8` (`Country` — `name`,
  `iso2`, `iso3`, `dial_code`, no slug), `geo.py:28` (`Region` — `slug`,
  unique **per country** via `unique_region_slug_per_country`).
- **Decision needed from:** Gareth, Ben Wood (Mojo).

### Problem

The live site has **69 flat root-level pages**, of which roughly 45 are
country or destination hubs: `/greece`, `/italy`, `/france`, `/corfu`,
`/paxos`, `/tuscany`, `/marrakech`. Villa URLs then sit one level down as
`/{destination}/{villa}` — `/corfu/villa-zogita`.

So the website's geography is **flat**: `/greece` and `/corfu` are siblings,
with no URL hierarchy, even though the hierarchy plainly exists in the data.
Our model is two-tier and hierarchical: `Country` → `Region` → `Property`.

Two consequences depend on an unmade decision:

1. **`Country` has no slug.** If country hubs are ever Res-fed, it needs one.
   If they are marketing pages, it never does.
2. **`Region.slug` is unique per country only** — enforced by
   `unique_region_slug_per_country`. The website's destination namespace is
   flat and global, so two same-slug regions in different countries would
   collide on the site. Whether that matters depends on the same decision.

⚠️ **Unverified:** whether any duplicate region slugs exist across countries
today. Check before treating this as theoretical — if any exist, the collision
is a live BUG rather than a constraint to tighten.

### The question

Do country and destination hub pages get their content from Res, or are they
marketing pages Mojo authors and owns?

**Proposed answer: Mojo owns them.** They are editorial and campaign surfaces
— hero imagery, positioning copy, curated villa selections, seasonal
messaging — none of which Res holds or should hold. Res supplies the *villas*
that appear on them, keyed by region, and nothing else.

If that is accepted:

- No `Country.slug`, no change to `Country` at all.
- `Region.slug` stays unique-per-country; the site keys its destination pages
  on `region.RES_ID` and treats slug as the advisory matching aid
  `_region_payload` already documents it as.
- The only geo obligation on the push is that each villa names its region by
  `RES_ID`, which it already does.

The alternative — Res-fed hubs — means adding `Country.slug`, promoting
`Region.slug` to globally unique (with a data fix if duplicates exist), and
accepting that our geo model now has to mirror a marketing site's URL
namespace. That is a real cost for benefit nobody has yet asked for.

### Acceptance

- A one-line decision recorded here and reflected in GAP-106's payload scope.
- If "Mojo owns them": an explicit note in GAP-106 that geo is villa-scoped
  only, so nobody later adds a hub-content push by inference.
- Either way: the duplicate-region-slug check above is run and its result
  recorded, since it stands alone as a data-quality question.

### Dependencies

- **GAP-106** — scope of the geo half of the payload.
- **GAP-103** (region/country edits never re-push) — if hubs ever become
  Res-fed, that ticket's `region` push kind becomes the delivery route, so
  answer this before GAP-103 is built rather than after.
- **GAP-104** open question (region re-slug moves every villa URL beneath it)
  — same area; a globally-unique region slug would change that answer too.
