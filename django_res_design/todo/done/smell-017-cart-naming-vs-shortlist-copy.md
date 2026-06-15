> **✅ RESOLVED (2026-06-15)** — Problem: Quote-builder code still said "cart" while the user-facing copy said "shortlist". Fix: Renamed cart to shortlist in the code. Commit: c670ac9.
>
> _Original ticket preserved below for context._

# SMELL-017 — Quote-builder code still says "cart"; user-facing copy now says "Shortlist"

- **Severity:** 🟡 Smell (naming drift only; no behaviour change)
- **Source:** 2026-06-11 copy change (cart → Shortlist)
- **Files:** `frontend/src/features/quotations/components/QuoteCart.tsx`,
  `QuoteCartLine.tsx`, `QuoteBuilder.tsx`, `SaveQuoteDialog.tsx`,
  `schemas.ts`, `lineTotals.ts`, `lib/format/money.ts`,
  `i18n/locales/*/quotations.json` (`builder.cart.*` keys), colocated tests

## Problem

The visible copy for the quote builder's staged-lines panel was renamed
from "cart" to "Shortlist" (en + el locales, 2026-06-11): a cart implies
the guest buys everything in it, whereas this is a curated set of stay
options the guest picks **one** of. The rename was deliberately
text-only, so the code now disagrees with the product language:

- Components: `QuoteCart`, `QuoteCartLine`, `CartActions`.
- i18n key namespace: `builder.cart.*` (both locales +
  `_machine_translated.json` entry).
- Comments throughout `quotations/` (and one each in
  `lib/format/money.ts`, `django_res/comms/migrations/0013_…`,
  `django_res/reservations/tests/test_quotation_render.py`) describe
  "the cart".

New work will copy whichever term it reads first, widening the drift.

## Proposed fix

Mechanical rename, one commit, no behaviour change:

- `QuoteCart` → `QuoteShortlist`, `QuoteCartLine` → `QuoteShortlistLine`,
  `CartActions` → `ShortlistActions` (files, imports, test descriptions).
- i18n: `builder.cart.*` → `builder.shortlist.*` in both locale files,
  `_machine_translated.json`, and every `t()` call site.
- Sweep comments mentioning "cart" in `features/quotations/` and the
  three stragglers above to say "shortlist".
- Leave Django migration **docstrings** alone if regenerating churn —
  comment-only edits there are fine; never edit applied migration logic.

## Acceptance

- `grep -ri cart frontend/src django_res` returns no quote-builder hits
  (the Greek "καλάθι υποδοχής" = welcome hamper in
  `inclusions_placeholder` is unrelated and stays).
- Full frontend quality gate passes (`eslint`, `prettier`, `tsc`,
  `vitest`).

## Resolution (2026-06-15)

Mechanical rename, one commit, **internal code only** — no wire contract
touched. The audit confirmed every `cart` hit was an internal identifier,
an i18n key, or a comment; none were serializer keys, API fields, or DB
columns, so the request/response shape is unchanged.

Done:

- Components: `QuoteCart` → `QuoteShortlist`, `QuoteCartLine` →
  `QuoteShortlistLine`, `CartActions` → `ShortlistActions` (files renamed
  via `git mv`, plus imports, props interfaces, and test descriptions).
- i18n: `builder.cart.*` → `builder.shortlist.*` in `en` + `el`
  `quotations.json` (key block renamed) and the
  `el/_machine_translated.json` entry; every `t()` call site updated.
- Swept "cart" comments → "shortlist" across `features/quotations/`,
  `lib/format/money.ts`, `reservations/tests/test_quotation_render.py`,
  and the comment-only docstring in
  `comms/migrations/0013_drop_quotation_grand_total.py` (migration logic
  untouched).

Acceptance grep is clean (the Greek `καλάθι υποδοχής` welcome-hamper
string is unrelated and left in place). Gates green: frontend `vitest`
(169 passed), `eslint`, `tsc`, `prettier`; backend `pytest`
(`test_quotation_render`, 14 passed), `ruff check`, `ruff format`,
`mypy`.
