# GAP-100 — A quotation is pushed to Zoho once, at send, and never again

- **Severity:** 🟠 Gap (the CRM cannot learn that a quote was accepted,
  expired or cancelled — by any route).
- **Source:** 2026-09-02 review of the Limitless quote Flow
  (`limitless_insert_quote`).
- **Files touched:**
  - `django_res/reservations/apps.py:268` —
    `register_zoho_flow(Quotation, kind="quote", …, auto_push=False)`.
  - `django_res/reservations/services/quotation_transmission.py:204–216` —
    `_queue_zoho_push`, the only caller.
  - `django_res/reservations/models/quotation.py:169–187` — `accept()`.

## Problem

Unlike `Enquiry` and `Booking`, `Quotation` is registered with
`auto_push=False`. The single push is fired by `_queue_zoho_push` from the
send path. So the CRM sees a quote exactly once, in status `sent`, and:

- **`accepted` never arrives.** Neither does `expired` or `cancelled`.
- **`is_selected` is always `false` on the wire.** It is set by `accept()`
  (`quotation.py:186`), which is strictly after the only push. So the field
  is in the payload, costs a column in every consumer's mapping, and can
  never be anything but `false` — which is exactly the field a consumer needs
  to tell *which* of a multi-option quote's alternatives won (CHECK-005
  item 1).
- **A revised, re-sent quote does push again** (`_queue_zoho_push` fires per
  send) — but Limitless' Flow is insert-only and discards it, so in practice
  nothing after the first send lands either way.

`auto_push=False` is the right default and should stay: quotes are edited
heavily in draft and a push per keystroke would be noise. The gap is that
`send` is the *only* event we treat as push-worthy.

## Proposal

Push on the status transitions that matter, not on every save:

- **`accept()`** — the important one. It is what makes `is_selected`
  meaningful and what tells the CRM the quote converted.
- **`cancel()`** and the expiry sweep — cheaper to add at the same time than
  to come back for, and both are states an operator would expect to see
  reflected.

Shape: call `enqueue_zoho_push(quotation)` from those transitions the way
`_queue_zoho_push` does from send, rather than flipping `auto_push=True`.
Keeping it explicit preserves the draft-noise property and keeps the set of
push-worthy events readable in one place — consider moving `_queue_zoho_push`
somewhere less send-specific if it gains three more callers.

Note `accept()` runs inside the `:convert` flow, which also creates and
pushes a `Booking`. Two pushes, two kinds, both wanted — but they will race,
and the booking references `quote.RES_ID`. Worth ordering the quote push
first, or accepting that Limitless' booking Flow already tolerates a missing
quote (it leaves `Quote_Name` empty rather than failing).

## Dependency

Half of this is theirs: an update branch on `limitless_insert_quote`, which
currently COQLs `Quotes` by `RES_ID` and returns early on a hit — see
**CHECK-005** item 3. Landing our half alone changes nothing observable, so
**coordinate**; do not close this ticket on our side and call the behaviour
fixed.

## Tests

- `accept()` enqueues exactly one `quote` push. (test)
- A cancelled quotation enqueues one push carrying `status: "cancelled"`.
  (test)
- The payload from an accept-time push has `is_selected: true` on exactly one
  line. (test — this is the whole point)
- Draft edits still enqueue nothing. (regression floor)

## 2026-09-22 update — the Limitless half has moved; ours is now the blocker

- **The Flow is no longer insert-only.** Greg's 2026-09-18 email: the Flows
  were reworked around upsert-by-`RES_ID` ("with the upsert behaviour it is
  easy to fix and re-run the flows"). His 2026-09-21 email reports the quote
  Flow revised and asks for **the full set of quote stage values** — i.e. the
  CRM now expects `status` to change over a quote's life. The dependency
  above (CHECK-005 item 3) looks unblocked; confirm on the 2026-09-22 call.
- **Replied 2026-09-22** with the five `QuotationStatus` values and the
  allowed transitions, stating plainly that today only send / re-send pushes,
  so live traffic arrives as `sent` only and acceptance reaches the CRM via
  the booking push. Asked him to map all five anyway.
- **Verification path already exists:** `zoho_send_sample --scenarios
  status_transitions` pushes one quote at SENT → ACCEPTED and another at
  SENT → CANCELLED (each yield is an explicit push, so it bypasses the
  send-only gate). Run it against the sandbox quote endpoint to check the
  upsert branch moves `Quote_Stage` *before* landing our half.
- **Proposal unchanged.** Enqueue from `accept()`, `cancel()` and the expiry
  sweep. Ordering note above still applies: on `:convert` the quote push
  should go before the booking push.

## Related

- **CHECK-005** items 1, 3 and 4 — the multi-option modelling question, the
  insert-only Flow, and the hardcoded `Quote_Stage` all depend on this.
- **GAP-097** — until delivery confirmation exists, a push landing on an
  insert-only Flow is indistinguishable from one that updated something.
