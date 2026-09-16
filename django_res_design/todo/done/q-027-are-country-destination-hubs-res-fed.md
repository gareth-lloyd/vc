# Q-027 — Are country and destination hub pages Res-fed, or marketing pages Mojo owns?

> **✅ SUPERSEDED (2026-09-16) — merged into [Q-026](../q-026-website-field-ownership-matrix.md)** as
> §"Merged from Q-027". Both are questions for Ben/Dave at Mojo that set the scope of GAP-106's payload; one ticket means one conversation. Nothing was decided or built by the
> merge; the open work continues there.
>
> _Original ticket preserved below for context._

- **Severity:** Question (decides whether `Country` needs a slug at all, and
  whether `Region` needs globally-unique ones — a schema question we should
  not answer by accident while building GAP-106).
- **Source:** URL-structure review of the live site, 2026-09-09 (Yoast
  sitemaps).
- **Files:** `django_res/properties/models/geo.py:8` (`Country` — `name`,
  `iso2`, `iso3`, `dial_code`, no slug), `geo.py:28` (`Region` — `slug`,
  unique **per country** via `unique_region_slug_per_country`).
- **Decision needed from:** Gareth, Ben Wood (Mojo).

## Problem

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

## The question

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

## Acceptance

- A one-line decision recorded here and reflected in GAP-106's payload scope.
- If "Mojo owns them": an explicit note in GAP-106 that geo is villa-scoped
  only, so nobody later adds a hub-content push by inference.
- Either way: the duplicate-region-slug check above is run and its result
  recorded, since it stands alone as a data-quality question.

## Dependencies

- **GAP-106** — scope of the geo half of the payload.
- **GAP-103** (region/country edits never re-push) — if hubs ever become
  Res-fed, that ticket's `region` push kind becomes the delivery route, so
  answer this before GAP-103 is built rather than after.
- **GAP-104** open question (region re-slug moves every villa URL beneath it)
  — same area; a globally-unique region slug would change that answer too.
