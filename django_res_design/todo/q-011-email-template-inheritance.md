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

- ~~Wire the resolver in `comms/services.py` to walk the chain.~~ ✅ Done — v1
  has a single layer (one active template per key, globally), which
  `EmailService._resolve_template` already implements. There is no `site` FK
  yet; the multi-layer walk lands with per-site white-labelling.
- ~~Tests covering each layer of override.~~ N/A for v1 — there is only one
  layer. The single-layer resolution is covered by
  `comms/tests/test_email_service.py` and `test_api_email_templates.py`.
- ~~Document in `10-comms.md`.~~ ✅ Done — see "Implementation status (v1)"
  under §Template admin UX requirements.
