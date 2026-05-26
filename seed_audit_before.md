# Seed-dev audit — BEFORE expansion

Command: `./manage.py seed_dev --scale small --profile mixed --seed 42`
Run token: `eaa0b7ed` (single fresh test DB; `pytest --nomigrations`)

## Stage summary

| stage              | created | errors | duration |
|--------------------|---------|--------|----------|
| users              | 4       | 0      | 0.02s    |
| properties         | 5       | 0      | 0.31s    |
| bookings           | 8       | 0      | 0.34s    |
| extra_quotations   | 2       | 0      | 0.02s    |
| orphan_enquiries   | 2       | 0      | 0.01s    |
| concierge_items    | 0       | 0      | 0.00s    |
| refunds            | 1       | 0      | 0.01s    |
| guest_preferences  | 3       | 0      | 0.01s    |
| property_lifecycle | 2       | 0      | 0.00s    |

## Per-model row counts

| model                                   | count | notes                                    |
|-----------------------------------------|------:|------------------------------------------|
| accounts.Contact                        | 7     |                                          |
| accounts.ContactEmail                   | 7     |                                          |
| accounts.ContactPhone                   | 7     |                                          |
| accounts.User                           | 4     |                                          |
| accounts.UserSession                    | **0** | gap — never written by seeder            |
| comms.EmailLog                          | **0** | gap — comms not exercised                |
| comms.EmailTemplate                     | **0** | gap                                      |
| comms.SmtpProfile                       | **0** | gap                                      |
| core.AuditLog                           | 58    |                                          |
| core.IdempotencyRecord                  | **0** | gap                                      |
| core.SystemSettings                     | **0** | gap                                      |
| core.UploadTicket                       | **0** | gap                                      |
| integrations.OAuthCredential            | **0** | gap                                      |
| integrations.SyncIssue                  | **0** | gap                                      |
| integrations.SyncRecord                 | **0** | gap                                      |
| integrations.SyncRun                    | **0** | gap                                      |
| payments.Payment                        | 8     |                                          |
| payments.PaymentEvent                   | 5     |                                          |
| payments.PaymentLine                    | **0** | gap — never written by services either   |
| payments.Refund                         | 1     |                                          |
| payments.SecurityDeposit                | **0** | gap (service called but no rows kept)    |
| payments.WebhookDelivery                | **0** | gap                                      |
| pricing.Currency                        | 1     | only GBP                                 |
| pricing.Discount                        | 5     |                                          |
| pricing.Extra                           | 5     |                                          |
| pricing.FxRate                          | **0** | gap                                      |
| pricing.RateCard                        | 5     |                                          |
| pricing.RatePlan                        | 5     |                                          |
| pricing.RateRule                        | 5     |                                          |
| pricing.VillaPricingSummary             | 5     | denorm written by signal                 |
| properties.ChangeOverRule               | **0** | gap                                      |
| properties.Collection                   | **0** | gap                                      |
| properties.CollectionMembership         | **0** | gap                                      |
| properties.Country                      | 6     | factory + ISO seed                       |
| properties.Feature                      | **0** | gap                                      |
| properties.FeatureCategory              | **0** | gap                                      |
| properties.GroupFinance                 | 5     | signal-created                           |
| properties.GroupSettings                | 5     | signal-created                           |
| properties.NearbyPlaceType              | **0** | gap                                      |
| properties.Property                     | 5     |                                          |
| properties.PropertyCapacity             | 5     |                                          |
| properties.PropertyCategory             | 4     |                                          |
| properties.PropertyContactAssignment    | **0** | gap                                      |
| properties.PropertyDescription          | 5     |                                          |
| properties.PropertyFinance              | 5     |                                          |
| properties.PropertyGroup                | 5     | one per property — no rotation           |
| properties.PropertyImage                | 5     | hero only, no gallery                    |
| properties.PropertyLocation             | 5     |                                          |
| properties.PropertyNearbyPlace          | **0** | gap                                      |
| properties.PropertySettings             | 5     |                                          |
| properties.Region                       | 5     |                                          |
| properties.Room                         | **0** | gap                                      |
| properties.RoomBeds                     | **0** | gap                                      |
| reservations.Booking                    | 8     |                                          |
| reservations.BookingConciergeItem       | **0** | gap (small profile only — pct_concierge picks 0)|
| reservations.BookingEvent               | 17    |                                          |
| reservations.BookingHold                | 10    |                                          |
| reservations.BookingNote                | **0** | gap                                      |
| reservations.Enquiry                    | 12    |                                          |
| reservations.EnquiryEvent               | 16    |                                          |
| reservations.EnquiryNote                | **0** | gap                                      |
| reservations.Guest                      | 8     |                                          |
| reservations.GuestPreference            | 3     |                                          |
| reservations.GuestPreferenceType        | 6     |                                          |
| reservations.Quotation                  | 10    |                                          |
| reservations.QuotationLine              | 10    |                                          |
| reservations.TermsVersion               | 1     | only one ACTIVE — no superseded          |

## Gap summary

23 concrete project models have **zero** rows after `seed_dev --scale small --profile mixed`:

- accounts: `UserSession`
- comms: `EmailLog`, `EmailTemplate`, `SmtpProfile`
- core: `IdempotencyRecord`, `SystemSettings`, `UploadTicket`
- integrations: `OAuthCredential`, `SyncIssue`, `SyncRecord`, `SyncRun`
- payments: `PaymentLine`, `SecurityDeposit`, `WebhookDelivery`
- pricing: `FxRate`
- properties: `ChangeOverRule`, `Collection`, `CollectionMembership`, `Feature`, `FeatureCategory`, `NearbyPlaceType`, `PropertyContactAssignment`, `PropertyNearbyPlace`, `Room`, `RoomBeds`
- reservations: `BookingConciergeItem` (small-profile only), `BookingNote`, `EnquiryNote`

Additional shape gaps:
- Currency: only GBP — properties never span EUR / USD.
- PropertyGroup: 1-to-1 with properties (one per via `SubFactory`) — no shared portfolio shape.
- PropertyImage: hero only — no gallery across `ImageKind` variants.
- TermsVersion: 1 active row, no superseded history.
