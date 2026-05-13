import { ReasonFormDialog } from "@/features/bookings/components/ReasonFormDialog";
import type { EnquiryId } from "@/lib/query/keys";
import { useCloseEnquiry } from "../hooks";
import { closeEnquiryInputSchema, type CloseEnquiryInput } from "../schemas";

interface CloseDialogProps {
  enquiryId: EnquiryId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Backend only models a single "lost" outcome — a successful enquiry becomes
// CONVERTED via convert(). So "Close" maps to lose.
export function CloseDialog({ enquiryId, open, onOpenChange }: CloseDialogProps) {
  const mutation = useCloseEnquiry(enquiryId);
  return (
    <ReasonFormDialog<CloseEnquiryInput>
      open={open}
      onOpenChange={onOpenChange}
      schema={closeEnquiryInputSchema}
      defaultValues={{ reason: "" }}
      reasonField="reason"
      submit={(values) => mutation.mutateAsync(values)}
      isPending={mutation.isPending}
      title="Close enquiry as lost?"
      description="Mark this enquiry as lost. You can reopen it later if needed."
      reasonLabel="Reason (optional)"
      reasonId="close-enquiry-reason"
      submitLabel="Close as lost"
      busyLabel="Closing…"
      keepLabel="Keep open"
      successMessage="Enquiry closed"
    />
  );
}
