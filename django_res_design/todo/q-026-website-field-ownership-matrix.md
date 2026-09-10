# Q-026 — Which fields does Res own on the website, and what happens to a site-side edit?

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
- Related **GAP-090** / **GAP-092** — the description-section set is part of
  what Res owns here; settle those first or the matrix names a moving target.
