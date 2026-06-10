# SMELL-013 — "One model per file" rule is fiction; de-facto rule is one aggregate per file

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `django_res/CLAUDE.md` (Principles §2: "One model per file in
  `<app>/models/*`"), 14 model modules

## Problem

The stated rule is violated by 14 files, including the most important ones:
`reservations/models/booking.py` (4 model classes — Booking, BookingGuest,
BookingHold, …), `reservations/models/enquiry.py` (3),
`properties/models/geo.py` (4), `pricing/models/rate.py` (3),
`accounts/models/contact.py` (3). The *actual* convention the codebase
follows is one **aggregate** per file — a root model plus its dependent
children/events — which is a perfectly good rule. A written rule the code
ignores trains readers (and agents) to ignore the rest of the document.

## Proposed fix

Doc-only. Amend `django_res/CLAUDE.md` Principles §2 to "one aggregate per
file: a root model and its dependent rows (children, events, through
models) live together; unrelated roots get their own module". Do **not**
churn the code to match the old wording — the file boundaries we have are
right.

## Acceptance

- CLAUDE.md wording matches the codebase; no code changes.

## Dependencies

None. Related: SMELL-012 (same doc-vs-reality cleanup pass).
