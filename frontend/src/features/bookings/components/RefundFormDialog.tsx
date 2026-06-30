import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import type { BookingId } from "@/lib/query/keys";
import { useCreateRefund } from "../hooks";
import {
  refundMethodOptions,
  refundPurposeTrackOptions,
  refundReasonCodeOptions,
  refundRequestInputSchema,
  type RefundRequestInput,
} from "../schemas";

interface Props {
  bookingId: BookingId;
  /** Shown for clarity — refunds are pinned to the booking's currency. */
  currencyCode: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const createDefaults: RefundRequestInput = {
  amount: "",
  purpose_track: "balance",
  reason_code: "other",
  method: "online_gateway",
  reason_notes: "",
};

export function RefundFormDialog({ bookingId, currencyCode, open, onOpenChange }: Props) {
  const { t } = useTranslation("bookings");
  const form = useForm<RefundRequestInput>({
    resolver: zodResolver(refundRequestInputSchema),
    defaultValues: createDefaults,
  });
  const purposeCtrl = useController({ control: form.control, name: "purpose_track" });
  const reasonCtrl = useController({ control: form.control, name: "reason_code" });
  const methodCtrl = useController({ control: form.control, name: "method" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRefund(bookingId);

  useEffect(() => {
    if (open) {
      form.reset(createDefaults);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: RefundRequestInput) => {
    setTopLevelError(null);
    try {
      await createMutation.mutateAsync(values);
      toast.success(t("refunds.toasts.requested"));
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
          <DialogTitle>{t("refunds.form_dialog.create_title")}</DialogTitle>
          <DialogDescription>{t("refunds.form_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="refund-amount">{t("refunds.form_dialog.fields.amount")}</Label>
              <Input
                id="refund-amount"
                inputMode="decimal"
                placeholder="0.00"
                autoFocus
                {...form.register("amount")}
                aria-invalid={!!form.formState.errors.amount}
              />
              {form.formState.errors.amount ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.amount.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label>{t("refunds.form_dialog.fields.currency")}</Label>
              {/* Pinned to the booking's currency server-side; shown for clarity. */}
              <p className="text-muted-foreground flex h-9 items-center text-sm">
                {currencyCode ?? "—"}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="refund-track">{t("refunds.form_dialog.fields.purpose_track")}</Label>
              <Select value={purposeCtrl.field.value} onValueChange={purposeCtrl.field.onChange}>
                <SelectTrigger
                  id="refund-track"
                  aria-label={t("refunds.form_dialog.fields.purpose_track")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {refundPurposeTrackOptions().map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="refund-method">{t("refunds.form_dialog.fields.method")}</Label>
              <Select value={methodCtrl.field.value} onValueChange={methodCtrl.field.onChange}>
                <SelectTrigger
                  id="refund-method"
                  aria-label={t("refunds.form_dialog.fields.method")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {refundMethodOptions().map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="refund-reason">{t("refunds.form_dialog.fields.reason_code")}</Label>
            <Select value={reasonCtrl.field.value} onValueChange={reasonCtrl.field.onChange}>
              <SelectTrigger
                id="refund-reason"
                aria-label={t("refunds.form_dialog.fields.reason_code")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {refundReasonCodeOptions().map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="refund-notes">{t("refunds.form_dialog.fields.notes")}</Label>
            <Textarea id="refund-notes" rows={2} {...form.register("reason_notes")} />
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
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending
                ? t("common:actions.saving")
                : t("refunds.form_dialog.submit_create")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
