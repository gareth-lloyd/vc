import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";
import i18n from "@/i18n";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import type { BookingId } from "@/lib/query/keys";
import { useRejectRefund } from "../hooks";
import type { Refund } from "../schemas";

const rejectInputSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, i18n.t("bookings:schema_errors.reason_required"))
    .max(500, i18n.t("bookings:schema_errors.reason_max")),
});
type RejectInput = z.infer<typeof rejectInputSchema>;

interface Props {
  bookingId: BookingId;
  refund: Refund;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RejectRefundDialog({ bookingId, refund, open, onOpenChange }: Props) {
  const { t } = useTranslation("bookings");
  const form = useForm<RejectInput>({
    resolver: zodResolver(rejectInputSchema),
    defaultValues: { reason: "" },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const rejectMutation = useRejectRefund(bookingId);

  useEffect(() => {
    if (open) {
      form.reset({ reason: "" });
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: RejectInput) => {
    setTopLevelError(null);
    try {
      await rejectMutation.mutateAsync({ refundId: refund.id, reason: values.reason });
      toast.success(t("refunds.toasts.rejected"));
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("refunds.reject_dialog.title")}</DialogTitle>
          <DialogDescription>
            {t("refunds.reject_dialog.description", { reference: refund.reference })}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="reject-reason">{t("refunds.reject_dialog.reason_label")}</Label>
            <Textarea
              id="reject-reason"
              rows={3}
              autoFocus
              {...form.register("reason")}
              aria-invalid={!!form.formState.errors.reason}
            />
            {form.formState.errors.reason ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.reason.message)}
              </p>
            ) : null}
          </div>

          {topLevelError ? (
            <p className="text-destructive text-sm" role="alert">
              {topLevelError}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
              {rejectMutation.isPending
                ? t("common:actions.saving")
                : t("refunds.reject_dialog.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
