# 08 · Quotation

The quotation is the priced offer that follows an enquiry. A quote is a set of property options (one or more villas at one or more date ranges) with line-item pricing, commission, discount, and inclusion text. Staff send it to the client; the client accepts; it becomes a booking.

## Files

| File | Workflows |
|---|---|
| [`construction.md`](./construction.md) | Search property options (uses the pricing engine), recalculate on field change, list quotations |
| [`persistence.md`](./persistence.md) | Save quotation master, save / edit quotation line items, apply discount, set commission |
| [`transmission.md`](./transmission.md) | Send quote to client by email, render quote HTML, push quote to Zoho |
| [`lifecycle.md`](./lifecycle.md) | Convert quote → booking, mark quote lost / expired |

## Entities touched

- `VillaQuotationMaster` — header: `Id`, `QuotationNo`, `EnquireId`, client details flattened, agent details flattened, `Stage` (Zoho stage enum: `Draft`/`Sent`/`Accepted`/`Lost`), `Owner` (Zoho owner email), `ClientNotes`, `PreferenceId` (multi-select Zoho tags), `FeatureId` (comma-string), `UnbrandedLinks`, `ZohoVilla`, `ZohoCountry`, `ZohoRegion`, audit columns
- `VillaQuotationDetail` — line items per (villa, date-range): `QuotationMasterId`, `VillaId`, `IsManual`, `FromDate`, `ToDate`, `Price`, `CurrencyId`, `IsBook`, `IsHold`, `Inclusion`
- `VillaClientDetail` — flattened client info (legacy stores it both denormalised on quote master and in this side table)

## Stored procedures

- `sp_quotation_master` — header upsert; output `@QuotationId` + `@QuotationNo` + `@Enquire`
- `sp_saveQuotationDetails` — line item write
- `sp_getQuotationMasterDataById` — read

Plus pricing-engine SPs (see `04-pricing/pricing-engine.md`).

## Cross-cutting notes

- **Quote stage ↔ Zoho stage** is direct: `ZohoQuoteStage` enum (`Draft`/`Sent`/`Accepted`/`Lost`) drives both the local `Stage` column and the Zoho `Stage` field.
- **Email send → enquiry status transition**: on successful quote send, `sp_updateEnquireStatus(EnquireId, 2)` flips the parent enquiry to `Quoted`.
- **HTML email**: quotes are rendered into an HTML email, **not** PDF. The committed code reads `quotation-rate-lookup.css` and inlines it into a wrapped HTML document.
- **Zoho Quote push happens after a successful email send** — not on save. A quote saved-but-not-sent does not appear in Zoho.

## Open design questions for the Django redesign

- The data-model design (`../05-reservations.md`) plans `reservations.Quotation` and `reservations.QuotationLine` with proper relational design and FKs to `Guest`, `Agent`, `Property`. Drop the denormalised copies on the master.
- Stage as `TextChoices`; explicit state transitions with audit rows.
- PDF generation should be a deliberate add (WeasyPrint / Playwright) — but consider whether HTML email is enough.
- Decide what "Expire" means — currently nothing expires quotes other than the linked Availability hold; consider an explicit quote expiry/SLA.
