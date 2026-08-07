import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
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
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import type { BookingId } from "@/lib/query/keys";
import { useSetDepositOverride } from "../hooks";
import { depositOverrideInputSchema, type DepositOverrideInput } from "../schemas";

interface Props {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current override, pre-filled for edit; blank when setting a fresh one. */
  currentAmount?: string | null;
}

// GAP-087: pin a per-booking deposit override. Clearing is a separate action
// on the FinanceTab (posts amount=null); this dialog only sets a concrete figure.
export function DepositOverrideDialog({ bookingId, open, onOpenChange, currentAmount }: Props) {
  const { t } = useTranslation("bookings");
  const form = useForm<DepositOverrideInput>({
    resolver: zodResolver(depositOverrideInputSchema),
    defaultValues: { amount: currentAmount ?? "", reason: "" },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useSetDepositOverride(bookingId);

  const handleSubmit = async (values: DepositOverrideInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync({ amount: values.amount, reason: values.reason });
      toast.success(t("finance.deposit_override.set_success"));
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
          <DialogTitle>{t("finance.deposit_override.dialog_title")}</DialogTitle>
          <DialogDescription>{t("finance.deposit_override.dialog_description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="deposit-override-amount">
              {t("finance.deposit_override.fields.amount")}
            </Label>
            <Input
              id="deposit-override-amount"
              inputMode="decimal"
              autoFocus
              {...form.register("amount")}
              aria-invalid={!!form.formState.errors.amount}
            />
            {form.formState.errors.amount ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.amount.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="deposit-override-reason">
              {t("finance.deposit_override.fields.reason")}
            </Label>
            <Textarea id="deposit-override-reason" rows={3} {...form.register("reason")} />
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
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending
                ? t("common:actions.saving")
                : t("finance.deposit_override.submit_label")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
