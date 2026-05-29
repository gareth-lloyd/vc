# Q-011 — Email template inheritance chain

- **Status:** ✅ **RESOLVED** (2026-05-27 critique) — `10-decisions.md`
  Deferred: "Per-villa email-template branding overrides — Legacy didn't
  have it; resist gold-plating." So the chain is **system default →
  site only** (no property layer).
- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 11
- **Blocks:** `comms.EmailTemplate` resolution logic, per-site
  white-labelling

## Question

The design assumes templates can be per-site (white-labelled). Confirm:

- Does inheritance go system default → site override → property
  override?
- Or is it system default → site (no property level)?

## Follow-up once answered

- Wire the resolver in `comms/services.py` to walk the chain.
- Tests covering each layer of override.
- Document in `10-comms.md`.
