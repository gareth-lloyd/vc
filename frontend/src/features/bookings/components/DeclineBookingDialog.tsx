import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("bookings");
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
      title={t("decline_dialog.title")}
      description={t("decline_dialog.description")}
      reasonLabel={t("decline_dialog.reason_label")}
      reasonId="decline-reason"
      submitLabel={t("decline_dialog.submit_label")}
      busyLabel={t("decline_dialog.busy_label")}
      keepLabel={t("decline_dialog.keep_label")}
      successMessage={t("decline_dialog.success_message")}
    />
  );
}
