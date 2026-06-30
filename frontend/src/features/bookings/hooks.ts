import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys, type BookingId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { ApiError } from "@/lib/api/errors";
import { fetchStatusCounts } from "@/lib/api/statusCounts";
import type { Paginated } from "@/types/api";
import {
  approveRefund,
  archiveBooking,
  bookingStatusCountsQuery,
  cancelBooking,
  cancelRefund,
  checkInBooking,
  checkOutBooking,
  confirmBooking,
  confirmConciergeItem,
  createBookingNote,
  createChargeItem,
  createRefund,
  captureSecurityDepositForDamages,
  createConciergeItem,
  createDamageClaim,
  executeRefund,
  declineBooking,
  deleteBookingNote,
  deleteChargeItem,
  deleteConciergeItem,
  deleteDamageClaim,
  fetchBalanceTrack,
  fetchBooking,
  fetchBookingActivity,
  fetchBookingChargeItems,
  fetchBookingConciergeItems,
  fetchBookingDamageClaims,
  fetchBookingEmails,
  fetchBookingNotes,
  fetchBookingRefunds,
  fetchBookings,
  fetchDepositTrack,
  fetchSecurityDeposit,
  fetchSecurityTrack,
  markPaid,
  rejectRefund,
  releaseSecurityDeposit,
  modifyBookingDates,
  modifyBookingGuests,
  requestPayment,
  resendBookingConfirmation,
  resendBookingEmail,
  restoreBooking,
  updateBookingNote,
  updateChargeItem,
  updateConciergeItem,
  updateDamageClaim,
  waiveTrack,
  withdrawDamageClaim,
  type TrackName,
} from "./api";
import type {
  BookingDetail,
  BookingFilters,
  BookingNote,
  BookingNoteWriteInput,
  CancelBookingInput,
  CaptureForDamagesInput,
  ChargeItemWriteInput,
  ConciergeItemWriteInput,
  DamageClaimWriteInput,
  DeclineBookingInput,
  MarkPaidInput,
  ModifyDatesInput,
  ModifyGuestsInput,
  RefundRequestInput,
  WaiveTrackInput,
} from "./schemas";

export const BOOKINGS_PAGE_SIZE = 50;

export function useBookings(filters: BookingFilters) {
  return useQuery({
    queryKey: queryKeys.bookings.list(filters),
    queryFn: () => fetchBookings(filters),
  });
}

export function useBookingStatusCounts(filters: BookingFilters) {
  const query = bookingStatusCountsQuery(filters);
  return useQuery({
    queryKey: queryKeys.bookings.statusCounts(query),
    queryFn: () => fetchStatusCounts("/bookings/status-counts", query),
  });
}

export function useBooking(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.detail, fetchBooking));
}

export function useBookingActivity(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.activity, fetchBookingActivity));
}

export function useBookingNotes(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.notes, fetchBookingNotes));
}

export function useBookingEmails(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.emails, fetchBookingEmails));
}

export function useResendBookingEmail(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId, idempotencyKey }: { emailId: number; idempotencyKey: string }) =>
      resendBookingEmail(bookingId, emailId, idempotencyKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.emails(bookingId) });
      // Resend writes an AuditLog row; refresh the activity timeline so the
      // operator sees their action without a manual reload.
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
    },
  });
}

export function useCreateBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BookingNoteWriteInput) => createBookingNote(bookingId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

interface UpdateNoteVars {
  noteId: number;
  input: Partial<BookingNoteWriteInput>;
}

export function useUpdateBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, input }: UpdateNoteVars) => updateBookingNote(bookingId, noteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

export function useDeleteBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId }: { noteId: number }) => deleteBookingNote(bookingId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

interface ToggleNotePinVars {
  noteId: number;
  is_pinned: boolean;
}

interface ToggleNotePinContext {
  snapshot: Paginated<BookingNote> | undefined;
}

function onActionSuccess(queryClient: QueryClient, bookingId: BookingId, updated: BookingDetail) {
  queryClient.setQueryData(queryKeys.bookings.detail(bookingId), updated);
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
  // The status tab-bar badges count by status, so any transition restains them.
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.statusCountsAll() });
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
}

export function useConfirmBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => confirmBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useCancelBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CancelBookingInput) => cancelBooking(bookingId, input),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useDeclineBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DeclineBookingInput) => declineBooking(bookingId, input),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useModifyBookingDates(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ModifyDatesInput) => modifyBookingDates(bookingId, input),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useModifyBookingGuests(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ModifyGuestsInput) => modifyBookingGuests(bookingId, input),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useArchiveBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => archiveBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useRestoreBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => restoreBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useCheckInBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => checkInBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useCheckOutBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => checkOutBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useResendBookingConfirmation(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => resendBookingConfirmation(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

// ----------------------------------------------------------------------
// Payment tracks
// ----------------------------------------------------------------------

const TRACK_KEY: Record<TrackName, (id: BookingId) => readonly unknown[]> = {
  deposit: queryKeys.bookings.deposit,
  balance: queryKeys.bookings.balance,
  security: queryKeys.bookings.security,
};

const TRACK_FETCHER = {
  deposit: fetchDepositTrack,
  balance: fetchBalanceTrack,
  security: fetchSecurityTrack,
} as const;

export function useDepositTrack(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.deposit, fetchDepositTrack));
}

export function useBalanceTrack(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.balance, fetchBalanceTrack));
}

export function useSecurityTrack(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.security, fetchSecurityTrack));
}

function invalidateTrack(queryClient: QueryClient, bookingId: BookingId, track: TrackName): void {
  queryClient.invalidateQueries({ queryKey: TRACK_KEY[track](bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
}

export function useRequestPayment(bookingId: BookingId, track: TrackName) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => requestPayment(bookingId, track),
    onSuccess: () => invalidateTrack(queryClient, bookingId, track),
  });
}

export function useMarkPaid(bookingId: BookingId, track: TrackName) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MarkPaidInput) => markPaid(bookingId, track, input),
    onSuccess: () => invalidateTrack(queryClient, bookingId, track),
  });
}

export function useWaiveTrack(bookingId: BookingId, track: TrackName) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: WaiveTrackInput) => waiveTrack(bookingId, track, input),
    onSuccess: () => invalidateTrack(queryClient, bookingId, track),
  });
}

// Re-export the existing fetcher map and trackName name for downstream tests.
export { TRACK_FETCHER };

// ----------------------------------------------------------------------
// Manual charge items
// ----------------------------------------------------------------------

export function useBookingChargeItems(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.chargeItems, fetchBookingChargeItems));
}

// A charge mutation moves the booking total, which moves the rail tiles
// (detail), the list row, the timeline and the resized deposit/balance
// schedule — invalidate them all, not just the charge list. (The concierge
// hooks invalidate narrowly because concierge money never enters `total`.)
function invalidateChargeDependents(queryClient: QueryClient, bookingId: BookingId): void {
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.chargeItems(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.deposit(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.balance(bookingId) });
}

export function useCreateChargeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChargeItemWriteInput) => createChargeItem(bookingId, input),
    onSuccess: () => invalidateChargeDependents(queryClient, bookingId),
  });
}

interface UpdateChargeVars {
  itemId: number;
  input: Partial<ChargeItemWriteInput>;
}

export function useUpdateChargeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, input }: UpdateChargeVars) => updateChargeItem(bookingId, itemId, input),
    onSuccess: () => invalidateChargeDependents(queryClient, bookingId),
  });
}

export function useDeleteChargeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => deleteChargeItem(bookingId, itemId),
    onSuccess: () => invalidateChargeDependents(queryClient, bookingId),
  });
}

// ----------------------------------------------------------------------
// Damage claims
// ----------------------------------------------------------------------

export function useBookingDamageClaims(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.damageClaims, fetchBookingDamageClaims));
}

// A damage claim never enters the booking `total` (the money moves on the SD
// capture, not the booking balance) and isn't yet surfaced on the booking
// detail or activity feed, so invalidate only the claim list. Widen this when
// the workflow-8 timeline/email integration starts emitting claim events.
function invalidateDamageClaimDependents(queryClient: QueryClient, bookingId: BookingId): void {
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.damageClaims(bookingId) });
}

export function useCreateDamageClaim(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DamageClaimWriteInput) => createDamageClaim(bookingId, input),
    onSuccess: () => invalidateDamageClaimDependents(queryClient, bookingId),
  });
}

interface UpdateDamageClaimVars {
  claimId: number;
  input: Partial<DamageClaimWriteInput>;
}

export function useUpdateDamageClaim(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, input }: UpdateDamageClaimVars) =>
      updateDamageClaim(bookingId, claimId, input),
    onSuccess: () => invalidateDamageClaimDependents(queryClient, bookingId),
  });
}

export function useWithdrawDamageClaim(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId }: { claimId: number }) => withdrawDamageClaim(bookingId, claimId),
    onSuccess: () => invalidateDamageClaimDependents(queryClient, bookingId),
  });
}

export function useDeleteDamageClaim(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId }: { claimId: number }) => deleteDamageClaim(bookingId, claimId),
    onSuccess: () => invalidateDamageClaimDependents(queryClient, bookingId),
  });
}

// ----------------------------------------------------------------------
// Security deposit (wf 8)
// ----------------------------------------------------------------------

export function useSecurityDeposit(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.securityDeposit, fetchSecurityDeposit));
}

// A release/capture moves the SD row state, the Payment-aggregate security
// track (`paid_amount`), and — for a capture — the consumed damage claim.
// Invalidate all three, plus the activity feed (the transition emits an event).
function invalidateSecurityDepositDependents(queryClient: QueryClient, bookingId: BookingId): void {
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.securityDeposit(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.security(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.damageClaims(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
}

export function useReleaseSecurityDeposit(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => releaseSecurityDeposit(bookingId),
    onSuccess: () => invalidateSecurityDepositDependents(queryClient, bookingId),
  });
}

export function useCaptureSecurityDepositForDamages(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CaptureForDamagesInput) =>
      captureSecurityDepositForDamages(bookingId, input),
    onSuccess: () => invalidateSecurityDepositDependents(queryClient, bookingId),
  });
}

// ----------------------------------------------------------------------
// Refunds (wf 17)
// ----------------------------------------------------------------------

export function useBookingRefunds(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.refunds, fetchBookingRefunds));
}

// A refund mutation moves the refund row, and a settled (succeeded) refund moves
// the booking finance and the relevant payment track's `paid_amount`. The cheap,
// correct move is to bust the refund list + the booking finance surfaces and all
// three tracks + the activity feed (each transition writes an event).
function invalidateRefundDependents(queryClient: QueryClient, bookingId: BookingId): void {
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.refunds(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.deposit(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.balance(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.security(bookingId) });
}

export function useCreateRefund(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RefundRequestInput) => createRefund(bookingId, input),
    onSuccess: () => invalidateRefundDependents(queryClient, bookingId),
  });
}

export function useApproveRefund(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ refundId }: { refundId: number }) => approveRefund(refundId),
    onSuccess: () => invalidateRefundDependents(queryClient, bookingId),
  });
}

export function useRejectRefund(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ refundId, reason }: { refundId: number; reason: string }) =>
      rejectRefund(refundId, reason),
    onSuccess: () => invalidateRefundDependents(queryClient, bookingId),
  });
}

export function useExecuteRefund(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ refundId }: { refundId: number }) => executeRefund(refundId),
    onSuccess: () => invalidateRefundDependents(queryClient, bookingId),
  });
}

export function useCancelRefund(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ refundId }: { refundId: number }) => cancelRefund(refundId),
    onSuccess: () => invalidateRefundDependents(queryClient, bookingId),
  });
}

// ----------------------------------------------------------------------
// Concierge items
// ----------------------------------------------------------------------

export function useBookingConciergeItems(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.conciergeItems, fetchBookingConciergeItems));
}

export function useCreateConciergeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ConciergeItemWriteInput) => createConciergeItem(bookingId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.conciergeItems(bookingId) });
    },
  });
}

interface UpdateConciergeVars {
  itemId: number;
  input: Partial<ConciergeItemWriteInput>;
}

export function useUpdateConciergeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, input }: UpdateConciergeVars) =>
      updateConciergeItem(bookingId, itemId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.conciergeItems(bookingId) });
    },
  });
}

export function useDeleteConciergeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => deleteConciergeItem(bookingId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.conciergeItems(bookingId) });
    },
  });
}

export function useConfirmConciergeItem(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => confirmConciergeItem(bookingId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.conciergeItems(bookingId) });
    },
  });
}

export function useToggleBookingNotePin(bookingId: BookingId) {
  const queryClient = useQueryClient();
  const key = queryKeys.bookings.notes(bookingId);
  return useMutation<BookingNote, Error, ToggleNotePinVars, ToggleNotePinContext>({
    mutationFn: ({ noteId, is_pinned }) => updateBookingNote(bookingId, noteId, { is_pinned }),
    onMutate: async ({ noteId, is_pinned }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueryData<Paginated<BookingNote>>(key);
      if (snapshot) {
        queryClient.setQueryData<Paginated<BookingNote>>(key, {
          ...snapshot,
          results: snapshot.results.map((n) => (n.id === noteId ? { ...n, is_pinned } : n)),
        });
      }
      return { snapshot };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.snapshot) queryClient.setQueryData(key, ctx.snapshot);
      const message = err instanceof ApiError ? err.detail : "Couldn't update pin";
      toast.error(message);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
