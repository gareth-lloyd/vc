# INV-006 — Live open questions harvested from the legacy workflow specs

- **Severity:** Investigation
- **Source:** the 2026-07-03 `django_res_design/` reorg. When the `workflows/`
  set was frozen into the [`legacy/`](../legacy/) tier, its labelled "Open
  design questions for the Django redesign" callouts were audited. Most were
  already decided or built; the items below are the residue that is **still
  open and tracked in no other ticket**. Captured here so freezing the legacy
  tier does not lose them.

## How to use this ticket

This is a holding pen, not a unit of work. Each item is a genuine open question
whose only prior home was a frozen legacy spec. When an area is next opened,
promote the relevant item to its own `gap-*` / `smell-*` / `q-*` ticket (or
resolve it inline and strike it here). Several items are security/hardening
reminders that may simply be actioned during the relevant app's next pass.
Line references are into `legacy/workflows/…` as of the reorg.

## Open items

### Identity & auth
1. **Login lockout / rate-limiting** — no throttle on repeated failed logins.
   `01-identity/authentication.md:38`.
2. **Password-reset flow hardening** — resist account enumeration, hash the
   reset token at rest, enforce a TTL, invalidate on use, and re-auth active
   sessions after a reset. `01-identity/password-management.md:35,67,93`.
3. **Staff-user GDPR erasure/anonymisation** — Q-010 covers guests; staff/User
   anonymisation is unspecified. `01-identity/user-administration.md:86`.

### Administration & taxonomy
4. **Currency precision** — per-currency `fractional_digits`, unique code,
   single-default enforcement. Cross-check overlap with SMELL-003 (resolved,
   decimal-places). `02-administration/financial-taxonomy.md:39`.
5. **Region ordering + named module-id constants** — replace magic module ids.
   `02-administration/geographic-taxonomy.md:77`.
6. **Secret handling** — move `apikey`/WP token/SMTP `serverpassword` out of the
   DB into env/secret storage (encrypt-at-rest or externalise), plus an SMTP
   test-send affordance. `02-administration/system-configuration.md:24,49,81`.
   (Adjacent to GAP-028.)

### Catalog / property
7. **Bulk-import robustness** — validation, transactionality, and sync on bulk
   property/room import. `03-catalog/README` + `03-catalog/property-rooms.md:87`.
8. **Image ordering + description-vs-toggle sync** — a real reorder mechanism
   for images and one authoritative rule reconciling description text vs boolean
   toggles. `03-catalog/property-imagery.md:88,107`.
9. **Geospatial + status audit** — lat/long → PostGIS `Point`; a
   `PropertyStatusEvent` audit trail; distance as `(value, unit)`.
   `03-catalog/property-master.md:46,79`, `03-catalog/property-nearby.md:41`.
10. **`BOOKING_CONFIRMATION` template authority** — establish the single owner
    of that template. `03-catalog/property-features.md:65`.
    (Note: attaching a bank account to the owner — `property-finance.md:65` —
    appears **decided against** in `../design/decisions.md`; confirm and drop.)

### Directory / people
11. **Named permission set** — replace the ~12 ad-hoc access/notify booleans
    with a named permission set. `05-directory/README.md:53`.

### Pricing
12. **Carry-forward `date_map` default rule** — the default mapping for
    next-year rate projection; currently only noted in `../design/decisions.md`
    "Open follow-ups". `legacy/workflows/04-pricing/seasons.md:109`.

### Availability
13. **Guest hold-expiry follow-up email** — a guest-facing notification when a
    hold expires (agent-facing one exists). Explicitly parked pending marketing.
    `06-availability/holds.md:104`.

### Enquiry
14. **Enquiry sign-up branch** — where the `IsSignUp` branch lands in the new
    enquiry model. `07-enquiry/README.md:38`.
15. **Staff-path confirmation-email toggle** — explicit "send confirmation
    email" control on staff-entered enquiries. `07-enquiry/enquiry-intake.md:127`.

### Quotation
16. **Per-villa line-overlap prevention** — stop a quotation carrying
    overlapping date lines for the same villa. `08-quotation/persistence.md:87`.
17. **CSS-inline vs MJML** — settle the quote-email rendering pipeline
    (inline-at-send vs authored MJML). `08-quotation/transmission.md:60`.

### Booking & payment
18. **Configurable payment-schedule templates** — templated deposit/balance
    schedules instead of hardcoded tiers.
    `09-booking/README.md`, `09-booking/payment-schedule.md:43`.
19. **Payment evidence upload** — attach proof to manually-recorded payments /
    schedule status changes. `09-booking/payment-schedule.md:71`,
    `10-payment/payment-collection.md:138`; plus transactional save of checkout
    personal info `10-payment/checkout-flow.md:62`.
20. **Concierge diff-patch + 4th schedule tier** — concierge save semantics and
    treating concierge as a fourth payment-schedule tier. Concierge is M2-
    deferred. `09-booking/concierge.md:35,73`.

### Integrations
21. **Zoho residuals** — wire the dead contact-push call, fix the `NewEnquire` /
    `VILLLA_MASTER` typo round-trips, and make the Stage→module mapping
    explicit. `11-integrations/zoho-crm.md:114,133,152,203`.
22. **WP endpoint-schema ownership** — who owns the WordPress response schema
    the sync targets. `11-integrations/public-website-sync.md:371`. (Nearest:
    GAP-028.)

## Disposition

None of the above blocks current work. Promote individually when the owning app
is next touched; delete the line here when it lands or is formally declined.
