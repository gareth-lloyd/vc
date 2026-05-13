import type { BookingId } from "@/lib/query/keys";
import { useDeclineBooking } from "../hooks";
import { declineBookingInputSchema, type DeclineBookingInput } from "../schemas";
import { ReasonFormDialog } from "./ReasonFormDialog";

interface DeclineBookingDialogProps {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: DeclineBookingInput = { reason: "" };

export function DeclineBookingDialog({ bookingId, open, onOpenChange }: DeclineBookingDialogProps) {
  const mutation = useDeclineBooking(bookingId);
  return (
    <ReasonFormDialog<DeclineBookingInput>
      open={open}
      onOpenChange={onOpenChange}
      schema={declineBookingInputSchema}
      defaultValues={DEFAULTS}
      reasonField="reason"
      submit={(values) => mutation.mutateAsync(values)}
      isPending={mutation.isPending}
      title="Decline this booking?"
      description="The booking will move to declined. Add a reason for the audit log."
      reasonLabel="Reason"
      reasonId="decline-reason"
      submitLabel="Decline booking"
      busyLabel="Declining…"
      keepLabel="Keep booking"
      successMessage="Booking declined"
    />
  );
}
