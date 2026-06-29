import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { BookingId } from "@/lib/query/keys";
import {
  bookingActivityResponseSchema,
  bookingChargeItemSchema,
  bookingChargeItemsResponseSchema,
  bookingConciergeItemSchema,
  bookingConciergeItemsResponseSchema,
  bookingDetailSchema,
  damageClaimSchema,
  damageClaimsResponseSchema,
  bookingEmailSchema,
  bookingEmailsResponseSchema,
  bookingListResponseSchema,
  bookingNoteSchema,
  bookingNotesResponseSchema,
  paymentRecordsListSchema,
  paymentTrackSchema,
  securityDepositSchema,
  type BookingChargeItem,
  type BookingConciergeItem,
  type BookingDetail,
  type BookingEmail,
  type BookingEvent,
  type BookingFilters,
  type BookingListItem,
  type BookingNote,
  type BookingNoteWriteInput,
  type CancelBookingInput,
  type ChargeItemWriteInput,
  type ConciergeItemWriteInput,
  type DamageClaim,
  type DamageClaimWriteInput,
  type DeclineBookingInput,
  type MarkPaidInput,
  type ModifyDatesInput,
  type ModifyGuestsInput,
  type PaymentRecord,
  type PaymentTrack,
  type CaptureForDamagesInput,
  type SecurityDeposit,
  type WaiveTrackInput,
} from "./schemas";

export type TrackName = "deposit" | "balance" | "security";

function toQuery(filters: BookingFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
    site: filters.site || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    check_in_after: filters.check_in_after || undefined,
    check_in_before: filters.check_in_before || undefined,
    check_out_after: filters.check_out_after || undefined,
    check_out_before: filters.check_out_before || undefined,
    exclude_terminal: filters.exclude_terminal ? "true" : undefined,
  };
}

export async function fetchBookings(filters: BookingFilters): Promise<Paginated<BookingListItem>> {
  const data = await apiGet<unknown>("/bookings", { query: toQuery(filters) });
  return bookingListResponseSchema.parse(data);
}

// The query that scopes the status counts: every filter EXCEPT the ones that
// don't change the totals (status/page/ordering). Exported so the hook keys on
// this stripped shape — keying on the full filters refetches identical counts
// on every chip click, page, or sort.
export function bookingStatusCountsQuery(filters: BookingFilters): QueryParams {
  const query = toQuery(filters);
  delete query.status;
  delete query.page;
  delete query.ordering;
  return query;
}

export async function fetchBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiGet<unknown>(`/bookings/${id}`);
  return bookingDetailSchema.parse(data);
}

export async function fetchBookingActivity(id: BookingId): Promise<BookingEvent[]> {
  const data = await apiGet<unknown>(`/bookings/${id}/activity`);
  return bookingActivityResponseSchema.parse(data);
}

export async function fetchBookingNotes(id: BookingId): Promise<Paginated<BookingNote>> {
  const data = await apiGet<unknown>(`/bookings/${id}/notes`);
  return bookingNotesResponseSchema.parse(data);
}

export async function fetchBookingEmails(id: BookingId): Promise<Paginated<BookingEmail>> {
  const data = await apiGet<unknown>(`/bookings/${id}/emails`);
  return bookingEmailsResponseSchema.parse(data);
}

export async function resendBookingEmail(
  bookingId: BookingId,
  emailId: number,
  idempotencyKey: string,
): Promise<BookingEmail> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/emails/${emailId}:resend`, {
    idempotency_key: idempotencyKey,
  });
  return bookingEmailSchema.parse(data);
}

export async function fetchBookingConciergeItems(
  id: BookingId,
): Promise<Paginated<BookingConciergeItem>> {
  const data = await apiGet<unknown>(`/bookings/${id}/concierge-items`);
  return bookingConciergeItemsResponseSchema.parse(data);
}

export async function createBookingNote(
  bookingId: BookingId,
  body: BookingNoteWriteInput,
): Promise<BookingNote> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/notes`, body);
  return bookingNoteSchema.parse(data);
}

export async function updateBookingNote(
  bookingId: BookingId,
  noteId: number,
  body: Partial<BookingNoteWriteInput>,
): Promise<BookingNote> {
  const data = await apiSend<unknown>("PATCH", `/bookings/${bookingId}/notes/${noteId}`, body);
  return bookingNoteSchema.parse(data);
}

export async function deleteBookingNote(bookingId: BookingId, noteId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bookings/${bookingId}/notes/${noteId}`);
}

export async function confirmBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:confirm`);
  return bookingDetailSchema.parse(data);
}

export async function cancelBooking(
  id: BookingId,
  body: CancelBookingInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:cancel`, body);
  return bookingDetailSchema.parse(data);
}

export async function declineBooking(
  id: BookingId,
  body: DeclineBookingInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:owner-decline`, body);
  return bookingDetailSchema.parse(data);
}

export async function modifyBookingDates(
  id: BookingId,
  body: ModifyDatesInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:modify-dates`, body);
  return bookingDetailSchema.parse(data);
}

export async function modifyBookingGuests(
  id: BookingId,
  body: ModifyGuestsInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:modify-guests`, body);
  return bookingDetailSchema.parse(data);
}

export async function archiveBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:archive`);
  return bookingDetailSchema.parse(data);
}

export async function restoreBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:restore`);
  return bookingDetailSchema.parse(data);
}

export async function checkInBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:check-in`);
  return bookingDetailSchema.parse(data);
}

export async function checkOutBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:check-out`);
  return bookingDetailSchema.parse(data);
}

export async function resendBookingConfirmation(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:resend-confirmation`);
  return bookingDetailSchema.parse(data);
}

// ----------------------------------------------------------------------
// Payment tracks
// ----------------------------------------------------------------------

export async function fetchDepositTrack(id: BookingId): Promise<PaymentTrack> {
  const data = await apiGet<unknown>(`/bookings/${id}/deposit`);
  return paymentTrackSchema.parse(data);
}

export async function fetchBalanceTrack(id: BookingId): Promise<PaymentTrack> {
  const data = await apiGet<unknown>(`/bookings/${id}/balance`);
  return paymentTrackSchema.parse(data);
}

export async function fetchSecurityTrack(id: BookingId): Promise<PaymentTrack> {
  const data = await apiGet<unknown>(`/bookings/${id}/security`);
  return paymentTrackSchema.parse(data);
}

export async function fetchTrackPayments(
  id: BookingId,
  track: TrackName,
): Promise<PaymentRecord[]> {
  const data = await apiGet<unknown>(`/bookings/${id}/${track}/payments`);
  return paymentRecordsListSchema.parse(data);
}

export async function requestPayment(id: BookingId, track: TrackName): Promise<PaymentTrack> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}/${track}:request-payment`);
  return paymentTrackSchema.parse(data);
}

export async function markPaid(
  id: BookingId,
  track: TrackName,
  body: MarkPaidInput,
): Promise<PaymentTrack> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}/${track}:mark-paid`, body);
  return paymentTrackSchema.parse(data);
}

export async function waiveTrack(
  id: BookingId,
  track: TrackName,
  body: WaiveTrackInput,
): Promise<PaymentTrack> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}/${track}:waive`, body);
  return paymentTrackSchema.parse(data);
}

// ----------------------------------------------------------------------
// Manual charge items
// ----------------------------------------------------------------------

export async function fetchBookingChargeItems(
  id: BookingId,
): Promise<Paginated<BookingChargeItem>> {
  const data = await apiGet<unknown>(`/bookings/${id}/charge-items`);
  return bookingChargeItemsResponseSchema.parse(data);
}

export async function createChargeItem(
  bookingId: BookingId,
  body: ChargeItemWriteInput,
): Promise<BookingChargeItem> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/charge-items`, body);
  return bookingChargeItemSchema.parse(data);
}

export async function updateChargeItem(
  bookingId: BookingId,
  itemId: number,
  body: Partial<ChargeItemWriteInput>,
): Promise<BookingChargeItem> {
  const data = await apiSend<unknown>(
    "PATCH",
    `/bookings/${bookingId}/charge-items/${itemId}`,
    body,
  );
  return bookingChargeItemSchema.parse(data);
}

export async function deleteChargeItem(bookingId: BookingId, itemId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bookings/${bookingId}/charge-items/${itemId}`);
}

// ----------------------------------------------------------------------
// Damage claims
// ----------------------------------------------------------------------

export async function fetchBookingDamageClaims(id: BookingId): Promise<Paginated<DamageClaim>> {
  const data = await apiGet<unknown>(`/bookings/${id}/damage-claims`);
  return damageClaimsResponseSchema.parse(data);
}

export async function createDamageClaim(
  bookingId: BookingId,
  body: DamageClaimWriteInput,
): Promise<DamageClaim> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/damage-claims`, body);
  return damageClaimSchema.parse(data);
}

export async function updateDamageClaim(
  bookingId: BookingId,
  claimId: number,
  body: Partial<DamageClaimWriteInput>,
): Promise<DamageClaim> {
  const data = await apiSend<unknown>(
    "PATCH",
    `/bookings/${bookingId}/damage-claims/${claimId}`,
    body,
  );
  return damageClaimSchema.parse(data);
}

export async function withdrawDamageClaim(
  bookingId: BookingId,
  claimId: number,
): Promise<DamageClaim> {
  const data = await apiSend<unknown>(
    "POST",
    `/bookings/${bookingId}/damage-claims/${claimId}:withdraw`,
  );
  return damageClaimSchema.parse(data);
}

export async function deleteDamageClaim(bookingId: BookingId, claimId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bookings/${bookingId}/damage-claims/${claimId}`);
}

// ----------------------------------------------------------------------
// Security deposit (wf 8)
// ----------------------------------------------------------------------

// The endpoint returns the SD row or a literal `null` body (HTTP 200) when the
// booking has none — the nullable parse handles both.
export async function fetchSecurityDeposit(id: BookingId): Promise<SecurityDeposit | null> {
  const data = await apiGet<unknown>(`/bookings/${id}/security/deposit`);
  return securityDepositSchema.nullable().parse(data);
}

// Release / claim return the Payment-aggregate track (the backend response);
// the panel re-reads the SD via its own query, which the hooks invalidate.
export async function releaseSecurityDeposit(id: BookingId): Promise<PaymentTrack> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}/security:release`);
  return paymentTrackSchema.parse(data);
}

export async function captureSecurityDepositForDamages(
  id: BookingId,
  body: CaptureForDamagesInput,
): Promise<PaymentTrack> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}/security:claim`, body);
  return paymentTrackSchema.parse(data);
}

// ----------------------------------------------------------------------
// Concierge items
// ----------------------------------------------------------------------

export async function createConciergeItem(
  bookingId: BookingId,
  body: ConciergeItemWriteInput,
): Promise<BookingConciergeItem> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/concierge-items`, body);
  return bookingConciergeItemSchema.parse(data);
}

export async function updateConciergeItem(
  bookingId: BookingId,
  itemId: number,
  body: Partial<ConciergeItemWriteInput>,
): Promise<BookingConciergeItem> {
  const data = await apiSend<unknown>(
    "PATCH",
    `/bookings/${bookingId}/concierge-items/${itemId}`,
    body,
  );
  return bookingConciergeItemSchema.parse(data);
}

export async function deleteConciergeItem(bookingId: BookingId, itemId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bookings/${bookingId}/concierge-items/${itemId}`);
}

export async function confirmConciergeItem(
  bookingId: BookingId,
  itemId: number,
): Promise<BookingConciergeItem> {
  const data = await apiSend<unknown>(
    "POST",
    `/bookings/${bookingId}/concierge-items/${itemId}:confirm`,
  );
  return bookingConciergeItemSchema.parse(data);
}
