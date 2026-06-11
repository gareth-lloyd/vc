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
