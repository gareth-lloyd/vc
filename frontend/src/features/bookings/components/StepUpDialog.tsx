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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { formatMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import { useExecuteRefund } from "../hooks";
import type { Refund } from "../schemas";

const stepUpInputSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, i18n.t("bookings:schema_errors.tfa_code_format")),
});
type StepUpInput = z.infer<typeof stepUpInputSchema>;

interface Props {
  bookingId: BookingId;
  refund: Refund;
  currency: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function StepUpDialog({ bookingId, refund, currency, open, onOpenChange }: Props) {
  const { t } = useTranslation("bookings");
  const form = useForm<StepUpInput>({
    resolver: zodResolver(stepUpInputSchema),
    defaultValues: { code: "" },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const executeMutation = useExecuteRefund(bookingId);

  useEffect(() => {
    if (open) {
      form.reset({ code: "" });
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: StepUpInput) => {
    setTopLevelError(null);
    try {
      await executeMutation.mutateAsync({ refundId: refund.id, tfaCode: values.code });
      toast.success(t("refunds.toasts.executed"));
      onOpenChange(false);
    } catch (error) {
      // invalid_tfa_code (400) / tfa_stepup_required (403) — and any other 4xx
      // (e.g. a 409 if a colleague already executed) — keep the dialog open with
      // the reason inline so the operator can retry with the next code. 5xx →
      // toast (mirrors RejectRefundDialog).
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
          <DialogTitle>{t("refunds.step_up.title")}</DialogTitle>
          <DialogDescription>
            {t("refunds.step_up.description", {
              amount: formatMoney(refund.amount, currency),
              reference: refund.reference,
            })}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="step-up-code">{t("refunds.step_up.code_label")}</Label>
            <Input
              id="step-up-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={6}
              {...form.register("code")}
              aria-invalid={!!form.formState.errors.code}
            />
            {form.formState.errors.code ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.code.message)}
              </p>
            ) : null}
            <p className="text-muted-foreground text-xs">{t("refunds.step_up.same_window_hint")}</p>
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
            <Button type="submit" disabled={executeMutation.isPending}>
              {executeMutation.isPending ? t("common:actions.saving") : t("refunds.step_up.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
