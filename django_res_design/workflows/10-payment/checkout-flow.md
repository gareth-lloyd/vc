# Checkout Flow

Captures guest personal info before payment, and accepts confirm/reject decisions from the gateway page.

## Redesign

The entire guest checkout journey moves off WordPress and is hosted
first-party in the React SPA, served by the Django API directly. Per
`10-decisions.md` ("Guest booking/checkout journey hosted in the SPA, not
WordPress"):

- The guest hits `portal.villacollective.com/booking?ref=<reference>` (the
  `Booking.checkout_url` set at booking creation — see
  `09-booking/booking-creation.md` and `05-reservations.md`).
- The page submits personal/additional info to a first-party Django endpoint
  (a booking-scoped checkout endpoint), **not** the WordPress-proxied
  `/api/wordpress/checkout/` (`SaveCheckoutInfo`) path described below.
- The Flywire return and webhook are handled first-party — direct-to-Django,
  not WordPress-proxied. See `08-integrations.md` for the Flywire integration
  surface.

Scope note: this is deliberately narrow — only the checkout page is in scope.
The deferred post-booking guest portal is **not** in scope. The legacy
descriptions below are preserved as reference for the behaviour being
reproduced.

## Save checkout personal info

**ID:** `PAYMENT.CHECKOUT.SAVE_INFO`
**Trigger:** Guest submits the checkout form on the WordPress public site; the site forwards to `POST /api/WordPressApi/Payment/SaveCheckoutInfo`.
**Actor:** Guest (unauthenticated).
**Legacy locus:** `PaymentController.cs:175-201`; `ResService.SaveCheckoutInfo` (`ResService.cs:4886-4958`); SPs `sp_checkout_personal_info`, `sp_checkout_additional_info`.

### Inputs
`CheckoutInfo`:
- `PersonalInfo` (`CheckoutPersonalInfo`):
  - `bookingId`, `bookingRefNo`
  - `title`, `firstName`, `lastName`
  - `addressLine1`, `addressLine2`, `town`, `postCode`, `country`, `countryCode`
  - `email`, `mobileNo`, `otherMobileNo`
  - `isAdditionalInfo` (bool — second guest follows)
  - `isConciergeService` (bool — guest opted into concierge upsell)
  - `conciergeDescription`, `conciergeId`
- `AdditionalInfo` (optional — same shape as PersonalInfo for a second guest)

### Process
1. Controller validates: `bookingId > 0`, `bookingRefNo` non-blank, and if `isAdditionalInfo` then `additionalInfo` not null.
2. Parse booking ref via `GetBookingNo()`.
3. Build SP parameters for `sp_checkout_personal_info` (out param `@Id` for the new row).
4. Execute; on success retrieve `@Id`.
5. If `isAdditionalInfo`: set `additionalInfo.CheckoutPesronalInfoId` `[TYPO]` to the new id; execute `sp_checkout_additional_info` with the second guest's fields.
6. If `isConciergeService`: `SentEmailAsync(EmailTemplate.UPGRADE_CONCIERGE_SERVICE_REQUEST, bookingRefNo)`.

### Outputs / side effects
- **DB write:** `CheckoutPersonalInfo` row; possibly `CheckoutAdditionalInfo` row.
- **Email out (conditional):** concierge upsell request to the operations team.

### Failure modes
- Personal info save succeeds but additional info save fails → orphan personal-info row.
- Concierge email fails → guest still sees success.

### Open questions
- Transactional save of personal + additional info.
- `CheckoutPesronalInfoId` typo to fix.

---

## Confirm or reject booking (gateway-side)

**ID:** `PAYMENT.CHECKOUT.CONFIRM_BOOKING`
**Trigger:** Staff action on the gateway page `POST /api/WordPressApi/Payment/ConfirmBooking`. Same code path as `BOOKING.LIFECYCLE.OWNER_CONFIRM`.
**Actor:** Staff (acting on owner's decision).
**Legacy locus:** `PaymentController.cs:204-233`; `ResService.cs:4536-4594`.

Cross-reference: see `09-booking/booking-confirmation.md` for full detail. The payment controller is a second entry point to the same workflow — the redesign should unify on one.

### Redesign

Resolved: the rebuild unifies on the single first-party booking-confirmation
workflow (`09-booking/booking-confirmation.md`). The payment-controller second
entry point (`POST /api/WordPressApi/Payment/ConfirmBooking`) is dropped — with
the checkout journey hosted in the SPA and served direct-to-Django (see the
Redesign note at the top of this file and `10-decisions.md`), there is no
WordPress gateway page and no need for a parallel payment-controller endpoint.

### Open questions
- ~~Two endpoints into one workflow is a smell. Consolidate.~~ Resolved — see
  Redesign above.

---

## Push payment dues to WordPress on success

**ID:** `PAYMENT.CHECKOUT.PUSH_DUES_TO_WORDPRESS`
**Trigger:** Internal — fires when a payment webhook reports `status == "guaranteed"` (see `PAYMENT.COLLECTION.WEBHOOK_RECEIVE`).
**Actor:** System.
**Legacy locus:** `ResService.cs:4374-4467` (`ResService.cs:4452` is the dispatch); `ResApiService.PushCheckOutDataToWP` at `ResApiService.cs:805-837` and `:1059-1071`.

### Inputs
- `GetCheckoutDetails(bookingRefNo)` → `List<PaymentDuesDates>` with `Id`, `Description`, `Amount`, `Date`, `IsPayment`

### Process
1. Build payload:
   ```
   {
     bookingId,
     PaymentDuesDates: [ { Id, Description, Amount, Date, IsPayment } ]
   }
   ```
2. `_apiService.PushCheckOutDataToWP(payload)` — fire-and-forget POST to `{site}/PaymentDuesDates` (also reached via `/Import_Booking` in some paths).

### Outputs / side effects
- **WordPress** payment-schedule view refreshed.
- **No retry**, no acknowledgement persisted locally.

### Failure modes
- WP unreachable → schedule diverges; guest sees stale due dates.

### Open questions
- Make this a retryable Celery task triggered by a `PaymentReceived` event.
