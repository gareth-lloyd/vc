import type { BookingId } from "@/lib/query/keys";
import { useCancelBooking } from "../hooks";
import { cancelBookingInputSchema, type CancelBookingInput } from "../schemas";
import { ReasonFormDialog } from "./ReasonFormDialog";

interface CancelBookingDialogProps {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: CancelBookingInput = { reason: "" };

export function CancelBookingDialog({ bookingId, open, onOpenChange }: CancelBookingDialogProps) {
  const mutation = useCancelBooking(bookingId);
  return (
    <ReasonFormDialog<CancelBookingInput>
      open={open}
      onOpenChange={onOpenChange}
      schema={cancelBookingInputSchema}
      defaultValues={DEFAULTS}
      reasonField="reason"
      submit={(values) => mutation.mutateAsync(values)}
      isPending={mutation.isPending}
      title="Cancel this booking?"
      description="This transitions the booking to cancelled. Add an optional reason for the audit log."
      reasonLabel="Reason (optional)"
      reasonId="cancel-reason"
      submitLabel="Cancel booking"
      busyLabel="Cancelling…"
      keepLabel="Keep booking"
      successMessage="Booking cancelled"
    />
  );
}
