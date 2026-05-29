# Q-013 — Rate-card "incomplete pricing" behaviour

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 13
- **Blocks:** Quotation builder UX, pricing engine fallbacks

## Question

Flow 2 step 4 references "if villa's rate card incomplete for some
nights, card flags 'Incomplete pricing — manual quote'". Confirm:

- Acceptable as-is — operator can type a price for missing nights, the
  villa stays selectable.
- OR hide the villa entirely from quotation results when pricing is
  incomplete.

The first option is the design's current direction; the second is
simpler but loses revenue.

## Follow-up once answered

- Pricing engine — return `incomplete=True` marker vs. exclude.
- Frontend — render the flag vs. hide the card.
