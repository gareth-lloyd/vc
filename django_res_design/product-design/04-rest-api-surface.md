# 04 — REST API Surface (Specification)

This document is a **table-of-contents level inventory** of endpoints the Django + DRF backend must expose. Payload schemas, status code enumeration, and DRF code are explicitly out of scope — they belong to the implementation phase. This file lists *what endpoints exist*, not *what they accept and return*.

---

## 1. API Conventions

### Base path & versioning
- All endpoints mounted under `/api/v1/`.
- Version is path-based (`/api/v1/`, `/api/v2/`). Minor additive changes are unversioned; breaking changes bump the major.
- Public-facing read endpoints (consumed by the marketing site or partner SPAs) are nested under `/api/v1/public/` with a separate auth/anon contract.
- Webhook receivers live under `/api/v1/webhooks/` and use signature-based auth, not the session/JWT auth.
- iCal feeds and other signed-URL endpoints live under `/api/v1/feeds/`.

### Resource naming
- Plural, lowercase, hyphenated (`/properties`, `/rate-cards`, `/email-templates`).
- Detail resource is `/{resource}/{id}` where `id` is the numeric PK or a slug, depending on resource (slug for `properties`, `regions`, `countries`, `sites`, `collections`; numeric otherwise).
- Sub-resources nest where the child has no meaningful identity outside the parent (`/properties/{id}/rooms`, `/bookings/{id}/concierge-items`).
- Cross-cutting child resources that the frontend treats as first-class (images, contacts, payments) are exposed both nested for write and flat for global list/search.

### Auth
- `Authorization: Bearer <token>` header on all authenticated endpoints. Token issued by `/auth/login` (short-lived access + refresh).
- Public endpoints accept anonymous; gated endpoints return 401 without a token, 403 with an insufficiently scoped token.
- Owner-portal token scope (`owner`) is a distinct auth scope from staff scopes (`staff`, `admin`).
- Site context derived from token claims; `X-Site` header may override for staff impersonating site context.

### Pagination
- Cursor pagination by default for endpoints expected to grow unbounded (`bookings`, `enquiries`, `email-logs`, `audit-log`, `payments`, `availability`).
- Page-number pagination for small bounded lists (`regions`, `countries`, `features`, `tags`, `currencies`, `roles`).
- Standard query params: `?cursor=`, `?limit=` (cursor); `?page=`, `?page_size=` (page). `limit` capped server-side.
- All list responses include `next` / `previous` and a `count` for page-number style.

### Filtering, search, sort
- Filtering uses query-string fields matching resource attributes (`?status=draft`, `?site=ibiza&region=balearics`).
- Multi-value filters via repeated key or comma-list (`?status=draft,confirmed`).
- Date range filters use `<field>_after` / `<field>_before` (e.g., `?check_in_after=2026-06-01`).
- Free-text search uses `?q=`.
- Sorting uses `?ordering=field,-other_field` (DRF convention).

### Includes / sparse fields
- Optional relation inclusion via `?include=images,rooms,features` to inline related collections. Default response is shallow (FK ids only).
- Sparse fieldsets via `?fields=id,name,slug` for list endpoints.

### List vs detail
- List endpoint returns lighter representation (no rich text, no nested collections).
- Detail endpoint returns full representation including small-cardinality nested collections (images, rooms, features) inline.

### Bulk operations
- Bulk create/update via `POST /{resource}/bulk` or `PATCH /{resource}/bulk` with an array body.
- Bulk delete via `POST /{resource}/bulk-delete`.
- Long-running bulk ops return a job handle and live under `/jobs/{id}` for polling.

### Action (verb) endpoints
- Non-CRUD state transitions use the colon-verb convention: `POST /bookings/{id}:confirm`, `POST /quotations/{id}:send`, `POST /enquiries/{id}:convert`.
- Action endpoints never accept a representation of the resource — only the action's parameters.
- Action endpoints return the updated resource (or a job handle if async).

### Webhooks
- Inbound: `POST /webhooks/{provider}` (stripe, zoho, airbnb, booking, vrbo). HMAC signature header verified.
- Outbound webhooks (we emit) are configured via `/webhook-subscriptions` resource.

### File upload
- Two-step: `POST /uploads:sign` returns a signed S3 (or equivalent) URL the client PUTs to. Then the client `POST`s the resulting key to the consuming resource (e.g., `POST /properties/{id}/images`).
- For small files (avatar, doc < 5 MB) direct multipart `POST` is also accepted at `POST /uploads`.

### Sub-resource convention
- Sub-resource list: `GET /properties/{id}/rates`.
- Sub-resource create: `POST /properties/{id}/rates`.
- Sub-resource detail: `GET /properties/{id}/rates/{rate_id}` OR `GET /rates/{rate_id}` (flat alias). Flat alias supported where the sub-resource has a globally unique id.

### Error format
- Standard problem-detail JSON shape with `code`, `detail`, `field_errors`. Implementation decides exact field names.

### Idempotency
- `Idempotency-Key` header honored on all `POST` action endpoints and payment-creating endpoints.

---

## 2. Endpoint Inventory

### 2.1 Auth & Profile

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/login` | Credential login, returns access + refresh tokens | anon |
| POST | `/auth/logout` | Invalidate refresh token | user |
| POST | `/auth/refresh` | Exchange refresh for new access token | anon (refresh) |
| POST | `/auth/password-reset:request` | Email reset link | anon |
| POST | `/auth/password-reset:confirm` | Submit new password with reset token | anon |
| POST | `/auth/2fa:challenge` | Begin 2FA challenge after primary auth | partial-auth |
| POST | `/auth/2fa:verify` | Submit OTP / TOTP code | partial-auth |
| POST | `/auth/2fa:enroll` | Begin TOTP enrollment | user |
| POST | `/auth/2fa:disable` | Disable 2FA for self | user |
| GET | `/auth/me` | Current user profile, site context, scopes | user |
| PATCH | `/auth/me` | Update own profile | user |
| POST | `/auth/me/password` | Change password (requires current) | user |
| GET | `/auth/permissions` | Discovery: what scopes/resources the caller can access | user |
| GET | `/auth/sessions` | List active sessions for self | user |
| DELETE | `/auth/sessions/{id}` | Revoke a session | user |
| POST | `/auth/magic-link:request` | Owner-portal passwordless link | anon |
| POST | `/auth/magic-link:consume` | Exchange magic-link token for session | anon |

---

### 2.2 Properties (Villas)

Core CRUD plus heavy sub-resource surface. Property is the most-edited entity in the admin UI.

#### Core
| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/properties` | List | filters: `status`, `category`, `group`, `region`, `country`, `site`, `collection`, `min_bedrooms`, `max_bedrooms`, `min_guests`, `q`; `include=`; `ordering=` |
| POST | `/properties` | Create | staff |
| GET | `/properties/{id}` | Detail | accepts numeric id or slug |
| PATCH | `/properties/{id}` | Partial update | |
| DELETE | `/properties/{id}` | Archive (soft delete) | |
| POST | `/properties/{id}:restore` | Un-archive | |
| POST | `/properties/{id}:duplicate` | Clone villa with sub-resources | |
| POST | `/properties/{id}:publish` | Status transition draft → live | |
| POST | `/properties/{id}:unpublish` | Status transition live → draft | |

#### Images
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/images` | List images, role-tagged |
| POST | `/properties/{id}/images` | Attach uploaded image (key from `/uploads:sign`) |
| PATCH | `/properties/{id}/images/{image_id}` | Update role tag, caption, alt |
| DELETE | `/properties/{id}/images/{image_id}` | Remove |
| POST | `/properties/{id}/images:reorder` | Reorder by id list |
| POST | `/properties/{id}/images:set-hero` | Designate hero |

#### Rooms
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/rooms` | List rooms with bed config |
| POST | `/properties/{id}/rooms` | Add room |
| PATCH | `/properties/{id}/rooms/{room_id}` | Update |
| DELETE | `/properties/{id}/rooms/{room_id}` | Remove |
| POST | `/properties/{id}/rooms:reorder` | Reorder |

#### Features / Amenities
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/features` | Attached features |
| PUT | `/properties/{id}/features` | Replace full set (idempotent multi-attach) |
| POST | `/properties/{id}/features` | Add one |
| DELETE | `/properties/{id}/features/{feature_id}` | Remove |

#### Tags
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/tags` | Service-type metadata tags |
| PUT | `/properties/{id}/tags` | Replace set |

#### Descriptions (rich text blocks)
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/descriptions` | All description sections (overview, house-rules, villa-info, further-info) |
| PUT | `/properties/{id}/descriptions/{section}` | Upsert one section |
| GET | `/properties/{id}/descriptions/{section}` | Fetch one |

#### Nearby points-of-interest
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/nearby` | List POIs |
| POST | `/properties/{id}/nearby` | Add POI |
| PATCH | `/properties/{id}/nearby/{poi_id}` | Update |
| DELETE | `/properties/{id}/nearby/{poi_id}` | Remove |

#### Contact mapping (which contacts are linked to this villa)
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/contacts` | List contact-property mappings (with role, permission flags) |
| POST | `/properties/{id}/contacts` | Attach contact with role + flags |
| PATCH | `/properties/{id}/contacts/{mapping_id}` | Update flags |
| DELETE | `/properties/{id}/contacts/{mapping_id}` | Detach |

#### Finance / settings on the villa
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/settings` | Currency, check-in/out, min nights, changeover day, pre-approval |
| PATCH | `/properties/{id}/settings` | Update settings |
| GET | `/properties/{id}/finance` | Commission defaults, payout config |
| PATCH | `/properties/{id}/finance` | Update |

#### Collections
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/collections` | Collections this property is in |
| PUT | `/properties/{id}/collections` | Replace set |

#### Importers / channel mappings
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/channel-mappings` | Airbnb/Booking.com/VRBO external IDs |
| PUT | `/properties/{id}/channel-mappings` | Upsert |
| POST | `/properties/{id}/channel-mappings:sync` | Trigger outbound sync to channel partners |
| POST | `/properties/{id}:import-from-zoho` | Pull from Zoho CRM |

---

### 2.3 Property Metadata

Catalogue resources — mostly thin CRUD, all admin-scoped writes, anon-readable for public endpoints under `/public/`.

#### Categories
| Method | Path |
|---|---|
| GET / POST | `/property-categories` |
| GET / PATCH / DELETE | `/property-categories/{id}` |

#### Groups (portfolio/brand)
| Method | Path |
|---|---|
| GET / POST | `/property-groups` |
| GET / PATCH / DELETE | `/property-groups/{id}` |

#### Collections (marketing sets)
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/collections` | |
| GET / PATCH / DELETE | `/collections/{slug}` | |
| GET | `/collections/{slug}/properties` | Properties in this collection |
| PUT | `/collections/{slug}/properties` | Replace set (bulk attach) |

#### Features (amenities)
| Method | Path |
|---|---|
| GET / POST | `/features` |
| GET / PATCH / DELETE | `/features/{id}` |
| GET / POST | `/feature-categories` |
| GET / PATCH / DELETE | `/feature-categories/{id}` |

#### Tags
| Method | Path |
|---|---|
| GET / POST | `/tags` |
| GET / PATCH / DELETE | `/tags/{id}` |

#### Regions
| Method | Path |
|---|---|
| GET / POST | `/regions` |
| GET / PATCH / DELETE | `/regions/{slug}` |
| GET | `/regions/{slug}/properties` |

#### Countries
| Method | Path |
|---|---|
| GET / POST | `/countries` |
| GET / PATCH / DELETE | `/countries/{code}` |

#### Currencies
| Method | Path |
|---|---|
| GET / POST | `/currencies` |
| GET / PATCH / DELETE | `/currencies/{code}` |
| GET | `/currencies/{code}/rates` | FX rates (if cached server-side) |

#### Sites (multi-tenant brands)
| Method | Path |
|---|---|
| GET / POST | `/sites` |
| GET / PATCH / DELETE | `/sites/{slug}` |
| GET | `/sites/{slug}/settings` |
| PATCH | `/sites/{slug}/settings` |

---

### 2.4 Pricing

Three-level hierarchy: **Season → Rate Card → Rate Rule**. Seasons are scoped to a property; rate cards live inside a season; rate rules carry the actual prices (one row per date sub-range × party-size band). Occupancy bands are not a separate resource — they are sibling rate rules sharing a date range with different party ranges. Date ranges are not a separate resource — they are columns on rate rule.

Backed by `pricing.RatePlan` (= Season), `pricing.RateCard`, and `pricing.RateRule` respectively.

#### Seasons
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/seasons` | List seasons for villa |
| POST | `/properties/{id}/seasons` | Create season |
| GET | `/seasons/{id}` | Detail (flat alias) — includes nested rate cards (with their rules inlined) |
| PATCH | `/seasons/{id}` | Update |
| DELETE | `/seasons/{id}` | Delete |
| POST | `/seasons/{id}:duplicate` | Clone with rate cards + rules |

#### Rate cards
| Method | Path | Purpose |
|---|---|---|
| GET | `/seasons/{id}/rate-cards` | List rate cards in season |
| POST | `/seasons/{id}/rate-cards` | Create (may include initial rules in body) |
| GET | `/rate-cards/{id}` | Detail (flat alias) — rules inlined by default |
| PATCH | `/rate-cards/{id}` | Update card metadata; rules can be replaced via nested array if `?replace_rules=true` |
| DELETE | `/rate-cards/{id}` | Delete |
| POST | `/rate-cards/{id}:duplicate` | Clone within or across seasons |

#### Rate rules (price rows)
Granular CRUD for individual rules. Use these when adding a single occupancy band or splitting a date sub-range without rewriting the whole card.
| Method | Path | Purpose |
|---|---|---|
| GET | `/rate-cards/{id}/rules` | List rules in card |
| POST | `/rate-cards/{id}/rules` | Add rule |
| GET | `/rules/{id}` | Detail (flat alias) |
| PATCH | `/rules/{id}` | Update |
| DELETE | `/rules/{id}` | Delete |

#### Extras (cleaning fee, pet fee, heating, linen, extra-bed, etc.)
Property-scoped catalogue of named charges added at quote time. Backed by `pricing.Extra` (see `04-pricing.md`). Each extra has a kind (`CLEANING`, `PET_FEE`, `HEATING`, `LINEN`, `EXTRA_BED`, `SERVICE_FEE`, `RESORT_FEE`, `OTHER`), a calc method, an amount, optional date and party-size windows, and an `is_mandatory` flag.

Tax and commission are **not** Extras — they live under property finance config (`/properties/{id}/finance`) and are applied automatically by the pricing engine.

| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/extras` | List extras for villa; filters: `kind`, `is_mandatory`, `is_active` |
| POST | `/properties/{id}/extras` | Create |
| GET | `/extras/{id}` | Detail (flat alias) |
| PATCH | `/extras/{id}` | Update |
| DELETE | `/extras/{id}` | Archive |
| POST | `/extras/{id}:duplicate` | Clone (optionally onto another property via body `target_property_id`) |

#### Website price display
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/price-display` | POA / min-max / symbol placement |
| PATCH | `/properties/{id}/price-display` | Update |

#### Pricing computation helper
| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/pricing:quote` | Compute total for property + dates + guests + opt-in extras | Body accepts `opt_in_extras: [<extra_id>, ...]`; mandatory extras are applied automatically. Stateless calc, used by quotation UI |
| POST | `/pricing:quote-bulk` | Compute for multiple villa/date combos | Used by multi-villa quote search |

---

### 2.5 Availability

Calendar reads are the highest-RPS endpoint group; expect heavy caching.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/properties/{id}/availability` | Calendar slice | `?from=&to=` required |
| POST | `/properties/{id}/availability` | Write block(s) — manual block, hold, owner-stay | accepts single or range |
| PATCH | `/availability/{id}` | Update one record | |
| DELETE | `/availability/{id}` | Clear block | |
| GET | `/availability` | Multi-villa availability lookup | `?property_ids=&from=&to=` |
| POST | `/availability:search` | Find villas matching date + guest criteria | filter: `region`, `country`, `min_bedrooms`, `features` |
| POST | `/availability:bulk-block` | Block range across many villas | admin |
| POST | `/availability/{id}:extend-hold` | Extend a hold's expiration | |
| POST | `/availability/{id}:release-hold` | Release a hold | |

Hold-expiration runs server-side on a schedule — no client endpoint.

---

### 2.6 Enquiries

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/enquiries` | List | filters: `status`, `site`, `assigned_to`, `source`, `created_after`, `created_before`, `q` |
| POST | `/enquiries` | Create (typically from public marketing site) | accepts anon via `/public/` mirror |
| GET | `/enquiries/{id}` | Detail | |
| PATCH | `/enquiries/{id}` | Update | |
| DELETE | `/enquiries/{id}` | Archive | |
| POST | `/enquiries/{id}:assign` | Assign owner / agent | |
| POST | `/enquiries/{id}:convert` | Convert to quotation | returns new quotation id |
| POST | `/enquiries/{id}:close` | Mark closed-lost / closed-won | |
| POST | `/enquiries/{id}:reopen` | Reopen | |
| GET | `/enquiries/{id}/activity` | Activity timeline (messages, status changes) | |
| POST | `/enquiries/{id}/notes` | Add internal note | |
| GET | `/enquiries/{id}/notes` | List notes | |
| POST | `/public/enquiries` | Public enquiry submission | anon, captcha-protected |

---

### 2.7 Quotations

Headers + line items; quote-send is a notable side-effecting action.

| Method | Path | Purpose |
|---|---|---|
| GET | `/quotations` | List, filter by `status`, `enquiry`, `guest`, `created_after` |
| POST | `/quotations` | Create header |
| GET | `/quotations/{id}` | Detail incl. lines |
| PATCH | `/quotations/{id}` | Update |
| DELETE | `/quotations/{id}` | Archive |
| POST | `/quotations/{id}:send` | Email quote to guest |
| POST | `/quotations/{id}:duplicate` | Clone |
| POST | `/quotations/{id}:convert` | Convert chosen line(s) to booking(s) |
| POST | `/quotations/{id}:withdraw` | Mark withdrawn |
| GET | `/quotations/{id}/pdf` | Rendered PDF (sync for small, async otherwise) |

#### Quotation lines (per-villa lines)
| Method | Path | Purpose |
|---|---|---|
| GET | `/quotations/{id}/lines` | List lines |
| POST | `/quotations/{id}/lines` | Add line |
| PATCH | `/quotations/{id}/lines/{line_id}` | Update |
| DELETE | `/quotations/{id}/lines/{line_id}` | Remove |
| POST | `/quotations/{id}/lines:reorder` | Reorder |

#### Helper
| Method | Path | Purpose |
|---|---|---|
| POST | `/quotations:search-villas` | Search villas suitable for a quote (date + guest + filter combo) — pricing-aware |

---

### 2.8 Bookings

The most action-heavy resource group. Lifecycle actions are POST verbs.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/bookings` | List | filters: `status`, `property`, `guest`, `site`, `check_in_after/before`, `check_out_after/before`, `assigned_to`, `q`; `ordering=`; `include=property,guest,payments` |
| POST | `/bookings` | Create | |
| GET | `/bookings/{id}` | Detail | |
| PATCH | `/bookings/{id}` | Update non-state fields | |
| DELETE | `/bookings/{id}` | Soft-archive | |

#### State transitions (side-effecting)
| Method | Path | Purpose |
|---|---|---|
| POST | `/bookings/{id}:confirm` | Move provisional → confirmed |
| POST | `/bookings/{id}:cancel` | Cancel (with reason) |
| POST | `/bookings/{id}:owner-approve` | Owner-portal approval |
| POST | `/bookings/{id}:owner-decline` | Owner-portal decline |
| POST | `/bookings/{id}:modify-dates` | Date change with availability + pricing re-check |
| POST | `/bookings/{id}:modify-guests` | Guest-count change |
| POST | `/bookings/{id}:archive` | Move to archive table |
| POST | `/bookings/{id}:restore` | Restore from archive |
| POST | `/bookings/{id}:check-in` | Mark guest checked in |
| POST | `/bookings/{id}:check-out` | Mark guest checked out |
| POST | `/bookings/{id}:resend-confirmation` | Re-send confirmation email |

#### Archive bookings (separate read surface)
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/archived` | List archived bookings (separate index) |
| GET | `/bookings/archived/{id}` | Detail |

#### Notes & activity
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/activity` | Timeline |
| GET | `/bookings/{id}/notes` | Notes |
| POST | `/bookings/{id}/notes` | Add note |
| PATCH / DELETE | `/bookings/{id}/notes/{note_id}` | Edit / remove |

#### Documents (contract, voucher)
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/documents` | List generated docs |
| POST | `/bookings/{id}/documents:generate` | Generate (contract/voucher), async job |
| GET | `/bookings/{id}/documents/{doc_id}` | Fetch metadata + signed URL |

---

### 2.9 Concierge Line Items (sub-resource of booking)

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/concierge-items` | List |
| POST | `/bookings/{id}/concierge-items` | Add |
| PATCH | `/bookings/{id}/concierge-items/{item_id}` | Update |
| DELETE | `/bookings/{id}/concierge-items/{item_id}` | Remove |
| POST | `/bookings/{id}/concierge-items:reorder` | Reorder |
| POST | `/bookings/{id}/concierge-items/{item_id}:confirm` | Mark confirmed |

---

### 2.10 Booking Payments — Deposit Track

Three parallel resource shapes (deposit, balance, security) — each is functionally the same surface but distinct paths so the UI can address each track independently.

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/deposit` | Current deposit status + scheduled amount + due date |
| PATCH | `/bookings/{id}/deposit` | Update schedule / amount |
| GET | `/bookings/{id}/deposit/payments` | List payment attempts on this track |
| POST | `/bookings/{id}/deposit/payments` | Record a manual payment |
| GET | `/bookings/{id}/deposit/payments/{payment_id}` | Detail |
| POST | `/bookings/{id}/deposit/payments/{payment_id}:capture` | Capture authorized charge |
| POST | `/bookings/{id}/deposit/payments/{payment_id}:void` | Void uncaptured |
| POST | `/bookings/{id}/deposit:request-payment` | Email pay-link to guest |
| POST | `/bookings/{id}/deposit:mark-paid` | Manual override |
| POST | `/bookings/{id}/deposit:waive` | Waive |

---

### 2.11 Booking Payments — Balance Track

Mirrors deposit track exactly, replacing `deposit` with `balance` in every path.

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/balance` | |
| PATCH | `/bookings/{id}/balance` | |
| GET / POST | `/bookings/{id}/balance/payments` | |
| GET | `/bookings/{id}/balance/payments/{payment_id}` | |
| POST | `/bookings/{id}/balance/payments/{payment_id}:capture` | |
| POST | `/bookings/{id}/balance/payments/{payment_id}:void` | |
| POST | `/bookings/{id}/balance:request-payment` | |
| POST | `/bookings/{id}/balance:mark-paid` | |
| POST | `/bookings/{id}/balance:waive` | |

---

### 2.12 Booking Payments — Security Deposit Track

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/security` | |
| PATCH | `/bookings/{id}/security` | |
| GET / POST | `/bookings/{id}/security/payments` | |
| GET | `/bookings/{id}/security/payments/{payment_id}` | |
| POST | `/bookings/{id}/security/payments/{payment_id}:capture` | |
| POST | `/bookings/{id}/security/payments/{payment_id}:hold` | Pre-auth hold |
| POST | `/bookings/{id}/security/payments/{payment_id}:release` | Release hold |
| POST | `/bookings/{id}/security/payments/{payment_id}:claim` | Convert hold to charge (damage) |
| POST | `/bookings/{id}/security:request-payment` | |
| POST | `/bookings/{id}/security:mark-paid` | |

---

### 2.13 Refunds

| Method | Path | Purpose |
|---|---|---|
| GET | `/refunds` | List; filters: `booking`, `status`, `created_after/before` |
| POST | `/bookings/{id}/refunds` | Initiate refund against a booking (parent context) |
| GET | `/refunds/{id}` | Detail |
| POST | `/refunds/{id}:approve` | Approve pending |
| POST | `/refunds/{id}:reject` | Reject |
| POST | `/refunds/{id}:execute` | Push to gateway |
| POST | `/refunds/{id}:cancel` | Cancel before execution |

---

### 2.14 Payments (flat, cross-booking)

| Method | Path | Purpose |
|---|---|---|
| GET | `/payments` | Global list across tracks; filters `track`, `gateway`, `status`, `currency`, date ranges |
| GET | `/payments/{id}` | Detail |
| GET | `/payment-methods` | List stored instruments/tokens for a guest |
| POST | `/guests/{id}/payment-methods` | Tokenize new instrument |
| DELETE | `/guests/{id}/payment-methods/{pm_id}` | Detach |
| GET | `/checkouts/{id}` | Settlement record detail |
| GET | `/checkouts` | List settlement records |

---

### 2.15 Contacts (Owners, Agents, Managers, Accountants)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/contacts` | List | filters: `role`, `site`, `country`, `q` |
| POST | `/contacts` | Create | |
| GET | `/contacts/{id}` | Detail | |
| PATCH | `/contacts/{id}` | Update | |
| DELETE | `/contacts/{id}` | Archive | |
| GET | `/contacts/{id}/emails` | List | |
| POST | `/contacts/{id}/emails` | Add | |
| PATCH / DELETE | `/contacts/{id}/emails/{email_id}` | | |
| POST | `/contacts/{id}/emails/{email_id}:set-primary` | | |
| GET | `/contacts/{id}/phones` | | |
| POST | `/contacts/{id}/phones` | | |
| PATCH / DELETE | `/contacts/{id}/phones/{phone_id}` | | |
| GET | `/contacts/{id}/properties` | Properties linked to this contact (reverse of property→contacts) | |
| POST | `/contacts/{id}:invite-portal` | Send owner-portal invite | |

---

### 2.16 Contact–Property Mapping (permissions & notifications)

The mapping is exposed both nested under property (see 2.2) and flat for permission-management UIs.

| Method | Path | Purpose |
|---|---|---|
| GET | `/contact-property-mappings` | Flat list; filters: `contact`, `property`, `role`, `notify_bookings` |
| GET | `/contact-property-mappings/{id}` | Detail |
| PATCH | `/contact-property-mappings/{id}` | Update flags |
| DELETE | `/contact-property-mappings/{id}` | Remove |

---

### 2.17 Guests / Clients

Distinct from `contacts`. These are the booking-side customers.

| Method | Path | Purpose |
|---|---|---|
| GET | `/guests` | List; filters: `country`, `site`, `q`, `created_after/before` |
| POST | `/guests` | Create |
| GET | `/guests/{id}` | Detail |
| PATCH | `/guests/{id}` | Update |
| DELETE | `/guests/{id}` | Archive (subject to GDPR rules — server may anonymize) |
| GET | `/guests/{id}/bookings` | Bookings for this guest |
| GET | `/guests/{id}/enquiries` | Enquiries for this guest |
| GET | `/guests/{id}/quotations` | |
| POST | `/guests/{id}:merge` | Merge duplicate guest records |
| POST | `/guests/{id}:anonymize` | GDPR erasure |

---

### 2.18 Users & Roles

| Method | Path | Purpose |
|---|---|---|
| GET | `/users` | List staff users; `?role=`, `?site=`, `?active=` |
| POST | `/users` | Create staff user |
| GET | `/users/{id}` | Detail |
| PATCH | `/users/{id}` | Update |
| DELETE | `/users/{id}` | Deactivate |
| POST | `/users/{id}:activate` | Reactivate |
| POST | `/users/{id}:reset-password` | Force reset (admin-initiated) |
| POST | `/users/{id}:reset-2fa` | Clear 2FA enrollment |
| GET | `/users/{id}/sessions` | Active sessions |
| DELETE | `/users/{id}/sessions/{session_id}` | Revoke |
| GET | `/roles` | List |
| POST | `/roles` | Create |
| GET | `/roles/{id}` | Detail with permission set |
| PATCH | `/roles/{id}` | Update |
| DELETE | `/roles/{id}` | Remove |
| GET | `/permissions` | Catalogue of available permission keys |

---

### 2.19 Email Templates & Email Logs

| Method | Path | Purpose |
|---|---|---|
| GET | `/email-templates` | List; filter `category`, `site` |
| POST | `/email-templates` | Create |
| GET | `/email-templates/{id}` | Detail |
| PATCH | `/email-templates/{id}` | Update |
| DELETE | `/email-templates/{id}` | Remove |
| POST | `/email-templates/{id}:preview` | Render with sample context |
| POST | `/email-templates/{id}:test-send` | Send to a test address |
| GET | `/email-logs` | List sent emails; filters: `booking`, `enquiry`, `guest`, `template`, `status`, date ranges |
| GET | `/email-logs/{id}` | Detail incl. rendered body |
| POST | `/email-logs/{id}:resend` | Re-send |
| GET | `/code-auth-logs` | Magic-link/code dispatch log |

---

### 2.20 Reports

All reports support `?from=&to=&site=&currency=` at minimum; specifics noted inline. Reports return JSON; same data is exportable via the export endpoint group (2.21).

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/reports/occupancy` | Occupancy by villa/region/period | `?group_by=property\|region\|month` |
| GET | `/reports/revenue` | Gross / net revenue | `?group_by=property\|month\|site` |
| GET | `/reports/owner-statements` | Per-owner statement | `?contact=&period=` |
| GET | `/reports/owner-statements/{contact_id}` | Single owner detail | |
| GET | `/reports/commissions` | Commission breakdown | |
| GET | `/reports/tax` | Tax collected | |
| GET | `/reports/payments` | Payment flow report | |
| GET | `/reports/refunds` | Refund summary | |
| GET | `/reports/enquiry-funnel` | Lead → quote → booking conversion | |

---

### 2.21 Exports (async job pattern)

| Method | Path | Purpose |
|---|---|---|
| POST | `/exports` | Create export job; body specifies report type + filters + format (csv/pdf/xlsx) |
| GET | `/exports` | List own export jobs |
| GET | `/exports/{id}` | Status + download URL when ready |
| DELETE | `/exports/{id}` | Cancel / delete |

Generic async-job surface (used by exports, doc generation, bulk ops):

| Method | Path | Purpose |
|---|---|---|
| GET | `/jobs/{id}` | Poll job status |
| POST | `/jobs/{id}:cancel` | Cancel |

---

### 2.22 Bulk Operations

Convention: `POST /{resource}/bulk` for create/update, `POST /{resource}/bulk-delete` for deletes. Notable bulk endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/properties/bulk` | Bulk create/update |
| POST | `/properties/bulk-delete` | |
| POST | `/properties/bulk:tag` | Apply tag/feature/collection to many |
| POST | `/availability/bulk-block` | (also listed in 2.5) |
| POST | `/rate-cards/bulk` | Mass-create rate cards across seasons |
| POST | `/contacts/bulk-import` | CSV import (async) |
| POST | `/guests/bulk-import` | CSV import (async) |
| POST | `/email-logs/bulk-resend` | |

---

### 2.23 Search (global / command-palette)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/search` | Global cross-entity search | `?q=`, `?types=properties,bookings,contacts,guests,enquiries`, `?limit=` |
| GET | `/search/suggest` | Autocomplete suggestions | type-ahead |
| GET | `/search/recent` | Caller's recent searches | |

---

### 2.24 iCal Feeds (signed URL, read-only)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/feeds/properties/{id}/ical` | iCal feed for a single villa | signed-URL token |
| GET | `/feeds/contacts/{id}/ical` | Owner's combined villas feed | signed-URL token |
| POST | `/properties/{id}/feeds/ical:rotate-token` | Rotate the signed URL | staff |
| GET | `/properties/{id}/feeds/ical` | Get current signed URL (admin view) | staff |

---

### 2.25 Channel Sync

#### Inbound (channels push to us)
| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/airbnb` | Inbound webhook |
| POST | `/webhooks/booking` | |
| POST | `/webhooks/vrbo` | |
| GET | `/channel-sync/inbound-log` | Audit of inbound events |

#### Outbound (we push)
| Method | Path | Purpose |
|---|---|---|
| GET | `/channel-sync/status` | Per-property channel sync state |
| POST | `/channel-sync:sync-property` | Trigger sync for a single property |
| POST | `/channel-sync:sync-all` | Site-wide trigger (admin) |
| GET | `/channel-sync/jobs` | Recent sync jobs |
| GET | `/channel-sync/jobs/{id}` | Job detail |

---

### 2.26 Zoho CRM Sync

| Method | Path | Purpose |
|---|---|---|
| GET | `/zoho/status` | Connection + last-sync timestamp |
| POST | `/zoho:connect` | Begin OAuth |
| POST | `/zoho:disconnect` | Revoke |
| POST | `/zoho:sync-contacts` | Trigger contact sync |
| POST | `/zoho:sync-properties` | Trigger property sync |
| POST | `/zoho:sync-enquiries` | Trigger enquiry sync |
| GET | `/zoho/sync-log` | Sync job history |
| GET | `/zoho/sync-log/{id}` | Job detail |
| POST | `/zoho/sync-log/{id}:retry` | Retry failed |

---

### 2.27 Payment Gateway Webhooks

| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/webhooks/stripe` | Stripe webhook | HMAC verified |
| POST | `/webhooks/{gateway}` | Generic per-gateway slot (paypal, adyen, etc.) | |
| GET | `/webhooks/log` | Audit log of inbound webhook attempts | admin |
| POST | `/webhooks/log/{id}:replay` | Replay a stored webhook | admin |

---

### 2.28 System Config / Settings

| Method | Path | Purpose |
|---|---|---|
| GET | `/system/settings` | Global config |
| PATCH | `/system/settings` | Update |
| GET | `/system/integrations` | Integration list + health |
| GET | `/system/integrations/{key}` | Detail |
| POST | `/system/integrations/{key}:test` | Connectivity test |

---

## 3. State-Transition Action Inventory

Consolidated list of named side-effecting actions, grouped by parent resource. All are `POST /{resource}/{id}:{action}`.

**Properties:** `publish`, `unpublish`, `duplicate`, `restore`, `import-from-zoho`. Image sub-action: `reorder`, `set-hero`.

**Enquiries:** `assign`, `convert`, `close`, `reopen`.

**Quotations:** `send`, `duplicate`, `convert`, `withdraw`. Lines: `reorder`.

**Bookings:** `confirm`, `cancel`, `owner-approve`, `owner-decline`, `modify-dates`, `modify-guests`, `archive`, `restore`, `check-in`, `check-out`, `resend-confirmation`. Documents: `generate`.

**Concierge items:** `confirm`, `reorder`.

**Deposit / Balance / Security tracks:** `request-payment`, `mark-paid`, `waive` (deposit/balance), and on the individual payment: `capture`, `void`. Security adds `hold`, `release`, `claim`.

**Refunds:** `approve`, `reject`, `execute`, `cancel`.

**Availability:** `extend-hold`, `release-hold`, `bulk-block`.

**Email templates:** `preview`, `test-send`. Logs: `resend`, `bulk-resend`.

**Channel sync:** `sync-property`, `sync-all`.

**Zoho:** `connect`, `disconnect`, `sync-contacts`, `sync-properties`, `sync-enquiries`. Jobs: `retry`.

**Webhooks:** `replay` (admin replay of stored inbound).

**Users:** `activate`, `reset-password`, `reset-2fa`.

**Contacts:** `invite-portal`. Emails: `set-primary`.

**Guests:** `merge`, `anonymize`.

**Auth:** `request`, `confirm` (password reset); `challenge`, `verify`, `enroll`, `disable` (2FA); `request`, `consume` (magic link).

**Pricing helpers:** `quote`, `quote-bulk` (stateless calc — listed here for completeness; not state-mutating but follows the verb form).

**Jobs:** `cancel`.

**Exports / Documents:** `generate` (documents), implicit job creation (exports).

---

## 4. Cross-Cutting Endpoints

### Health & ops
| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/health` | Liveness | anon |
| GET | `/health/ready` | Readiness (DB, cache, gateway connectivity) | anon |
| GET | `/system/version` | Build version, git sha | anon |
| GET | `/system/time` | Server clock (for client skew detection) | anon |

### Audit log
| Method | Path | Purpose |
|---|---|---|
| GET | `/audit-log` | Query log; filters: `actor`, `entity_type`, `entity_id`, `action`, date range |
| GET | `/audit-log/{id}` | Detail |
| GET | `/{resource}/{id}/audit-log` | Scoped audit log per entity (alias) |

### Notifications (in-app)
| Method | Path | Purpose |
|---|---|---|
| GET | `/notifications` | List own notifications; `?unread=true` |
| GET | `/notifications/{id}` | Detail |
| POST | `/notifications/{id}:mark-read` | |
| POST | `/notifications:mark-all-read` | |
| DELETE | `/notifications/{id}` | Dismiss |
| GET | `/notification-preferences` | Channel + topic prefs |
| PATCH | `/notification-preferences` | Update |

### Feature flags
| Method | Path | Purpose |
|---|---|---|
| GET | `/feature-flags` | Caller's effective flags |
| GET | `/feature-flags/all` | All flags (admin) |
| PATCH | `/feature-flags/{key}` | Update (admin) |

### Uploads
| Method | Path | Purpose |
|---|---|---|
| POST | `/uploads:sign` | Get presigned PUT URL |
| POST | `/uploads` | Direct multipart upload (small files) |
| GET | `/uploads/{key}` | Metadata lookup |

### Public / unauthenticated mirror
The marketing-site read surface lives under `/api/v1/public/` and exposes a curated subset:
- `GET /public/properties`, `GET /public/properties/{slug}`
- `GET /public/regions`, `GET /public/regions/{slug}/properties`
- `GET /public/collections`, `GET /public/collections/{slug}/properties`
- `GET /public/features`, `GET /public/tags`
- `POST /public/enquiries`
- `POST /public/availability:search`, `POST /public/pricing:quote`
