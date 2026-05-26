# Seed-dev audit — AFTER expansion

Command: `./manage.py seed_dev --scale small --profile mixed --seed 42`
Run: single fresh test DB (`pytest --nomigrations`).

## Stage summary

| stage              | created | errors | notes                                |
|--------------------|---------|--------|--------------------------------------|
| bookings           | 8       | 0      | unchanged                            |
| collections        | 6       | 0      | NEW                                  |
| concierge_items    | 2       | 0      | was 0 (floor at 1 in stage)          |
| contacts           | 4       | 0      | NEW                                  |
| extra_quotations   | 2       | 0      | unchanged                            |
| features           | 61      | 0      | NEW                                  |
| gallery            | 38      | 0      | NEW (non-HERO PropertyImages)        |
| groups             | 3       | 0      | NEW                                  |
| guest_preferences  | 1       | 0      | unchanged                            |
| integrations       | 57      | 0      | NEW (creds + runs + records + issues)|
| nearby_places      | 23      | 0      | NEW                                  |
| notes              | 7       | 0      | NEW                                  |
| orphan_enquiries   | 2       | 0      | unchanged                            |
| properties         | 5       | 0      | + ChangeOverRule per 3rd property    |
| property_lifecycle | 2       | 0      | unchanged                            |
| refunds            | 1       | 0      | unchanged                            |
| rooms              | 32      | 0      | NEW                                  |
| system_setup       | 24      | 0      | NEW (multi-currency + FX + templates)|
| users              | 4       | 0      | unchanged                            |
| webhooks           | 4       | 0      | NEW                                  |

## Gap closures (vs `seed_audit_before.md`)

| model                                    | before | after | status         |
|------------------------------------------|--------|-------|----------------|
| comms.EmailTemplate                      | 0      | 5     | CLOSED         |
| comms.SmtpProfile                        | 0      | 1     | CLOSED         |
| integrations.OAuthCredential             | 0      | 1     | CLOSED         |
| integrations.SyncIssue                   | 0      | 24    | CLOSED         |
| integrations.SyncRecord                  | 0      | 20    | CLOSED         |
| integrations.SyncRun                     | 0      | 12    | CLOSED         |
| payments.WebhookDelivery                 | 0      | 4     | CLOSED         |
| pricing.FxRate                           | 0      | 12    | CLOSED         |
| properties.ChangeOverRule                | 0      | 2     | CLOSED         |
| properties.Collection                    | 0      | 4     | CLOSED         |
| properties.CollectionMembership          | 0      | 6     | CLOSED         |
| properties.Feature                       | 0      | 20    | CLOSED         |
| properties.FeatureCategory               | 0      | 5     | CLOSED         |
| properties.NearbyPlaceType               | 0      | 5     | CLOSED         |
| properties.PropertyContactAssignment     | 0      | 9     | CLOSED         |
| properties.PropertyNearbyPlace           | 0      | 23    | CLOSED         |
| properties.Room                          | 0      | 32    | CLOSED         |
| properties.RoomBeds                      | 0      | 32    | CLOSED         |
| reservations.BookingConciergeItem        | 0      | 2     | CLOSED         |
| reservations.BookingNote                 | 0      | 3     | CLOSED         |
| reservations.EnquiryNote                 | 0      | 4     | CLOSED         |
| pricing.Currency                         | 1      | 3     | shape closed   |
| properties.PropertyGroup                 | 5      | 3     | shape closed   |
| properties.PropertyImage                 | 5      | 43    | shape closed   |
| reservations.TermsVersion                | 1      | 3     | shape closed   |

## Still-empty (out of scope for this pass)

| model                       | reason                                                        |
|-----------------------------|---------------------------------------------------------------|
| accounts.UserSession        | login-flow side effect; not seeded                            |
| core.IdempotencyRecord      | service-write only; not yet seeded                            |
| core.SystemSettings         | single-row config; not yet seeded                             |
| core.UploadTicket           | upload-flow side effect; not seeded                           |
| payments.PaymentLine        | engine-emitted line items; pre-existing seed gap              |
| payments.SecurityDeposit    | service called but no row materialised; pre-existing gap      |

These were never written by the legacy seeder either — they fall outside the
v2 expansion brief and are tracked here so they can be picked up later.
