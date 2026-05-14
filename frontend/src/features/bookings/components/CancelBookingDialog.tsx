import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("bookings");
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
      title={t("cancel_dialog.title")}
      description={t("cancel_dialog.description")}
      reasonLabel={t("cancel_dialog.reason_label")}
      reasonId="cancel-reason"
      submitLabel={t("cancel_dialog.submit_label")}
      busyLabel={t("cancel_dialog.busy_label")}
      keepLabel={t("cancel_dialog.keep_label")}
      successMessage={t("cancel_dialog.success_message")}
    />
  );
}
