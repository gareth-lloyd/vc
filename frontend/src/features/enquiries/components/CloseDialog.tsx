import { useTranslation } from "react-i18next";
import { ReasonFormDialog } from "@/features/bookings/components/ReasonFormDialog";
import type { EnquiryId } from "@/lib/query/keys";
import { useCloseEnquiry } from "../hooks";
import { closeEnquiryInputSchema, type CloseEnquiryInput } from "../schemas";

interface CloseDialogProps {
  enquiryId: EnquiryId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: CloseEnquiryInput = { reason: "" };

// Backend only models a single "lost" outcome — a successful enquiry becomes
// CONVERTED via convert(). So "Close" maps to lose.
export function CloseDialog({ enquiryId, open, onOpenChange }: CloseDialogProps) {
  const { t } = useTranslation("enquiries");
  const mutation = useCloseEnquiry(enquiryId);
  return (
    <ReasonFormDialog<CloseEnquiryInput>
      open={open}
      onOpenChange={onOpenChange}
      schema={closeEnquiryInputSchema}
      defaultValues={DEFAULTS}
      reasonField="reason"
      submit={(values) => mutation.mutateAsync(values)}
      isPending={mutation.isPending}
      title={t("close.title")}
      description={t("close.description")}
      reasonLabel={t("close.reason_label")}
      reasonId="close-enquiry-reason"
      submitLabel={t("close.submit_label")}
      busyLabel={t("close.busy_label")}
      keepLabel={t("close.keep_label")}
      successMessage={t("close.success_message")}
    />
  );
}
