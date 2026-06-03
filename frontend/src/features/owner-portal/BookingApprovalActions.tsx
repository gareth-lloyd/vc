import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { BookingId } from "@/lib/query/keys";
import { useApproveBooking, useDeclineBooking } from "./hooks";
import { declineBookingInputSchema, type DeclineBookingInput } from "./schemas";

interface Props {
  bookingId: BookingId;
}

// Approve / Decline affordance for a booking awaiting the owner's decision.
// Render only when the booking is PENDING_OWNER_APPROVAL and can_approve is true.
export function BookingApprovalActions({ bookingId }: Props) {
  const { t } = useTranslation("owner");
  const [declineOpen, setDeclineOpen] = useState(false);
  const approveMutation = useApproveBooking(bookingId);
  const declineMutation = useDeclineBooking(bookingId);

  const handleApprove = async () => {
    try {
      await approveMutation.mutateAsync();
      toast.success(t("approval.toasts.approved"));
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };

  return (
    <>
      <Button size="sm" onClick={handleApprove} disabled={approveMutation.isPending}>
        {t("booking_detail.approve")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setDeclineOpen(true)}
        disabled={approveMutation.isPending}
      >
        {t("booking_detail.decline")}
      </Button>
      {declineOpen ? (
        <DeclineDialog
          mutation={declineMutation}
          open={declineOpen}
          onOpenChange={setDeclineOpen}
        />
      ) : null}
    </>
  );
}

interface DeclineDialogProps {
  mutation: ReturnType<typeof useDeclineBooking>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function DeclineDialog({ mutation, open, onOpenChange }: DeclineDialogProps) {
  const { t } = useTranslation("owner");
  const form = useForm<DeclineBookingInput>({
    resolver: zodResolver(declineBookingInputSchema),
    defaultValues: { reason: "" },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      form.reset({ reason: "" });
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: DeclineBookingInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync(values.reason);
      toast.success(t("approval.toasts.declined"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  const reasonError = form.formState.errors.reason;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("approval.decline_dialog.title")}</DialogTitle>
          <DialogDescription>{t("approval.decline_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="decline-reason">{t("approval.decline_dialog.reason_label")}</Label>
            <Textarea
              id="decline-reason"
              rows={4}
              autoFocus
              {...form.register("reason")}
              aria-invalid={!!reasonError}
            />
            {reasonError ? (
              <p className="text-destructive text-sm" role="alert">
                {t(reasonError.message ?? "")}
              </p>
            ) : null}
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" variant="destructive" disabled={mutation.isPending}>
              {mutation.isPending
                ? t("common:actions.saving")
                : t("approval.decline_dialog.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
