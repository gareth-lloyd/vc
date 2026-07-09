import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { fieldErrorText } from "@/lib/forms/fieldError";
import type { BookingId } from "@/lib/query/keys";
import { useCreateChargeItem, useUpdateChargeItem } from "../hooks";
import {
  chargeItemWriteInputSchema,
  type BookingChargeItem,
  type ChargeItemWriteInput,
} from "../schemas";

interface CommonProps {
  bookingId: BookingId;
  currencyCode: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  item: BookingChargeItem;
}

type Props = CreateProps | EditProps;

const createDefaults: ChargeItemWriteInput = {
  label: "",
  amount: "",
  notes: "",
  commissionable: true,
};

function defaultsFromItem(item: BookingChargeItem): ChargeItemWriteInput {
  return {
    label: item.label,
    amount: item.amount,
    notes: item.notes ?? "",
    commissionable: item.commissionable ?? true,
  };
}

export function ChargeItemFormDialog(props: Props) {
  const { t } = useTranslation("bookings");
  const { bookingId, currencyCode, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<ChargeItemWriteInput>({
    resolver: zodResolver(chargeItemWriteInputSchema),
    defaultValues: isCreate ? createDefaults : defaultsFromItem(props.item),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const commissionable = form.watch("commissionable") ?? true;

  const createMutation = useCreateChargeItem(bookingId);
  const updateMutation = useUpdateChargeItem(bookingId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  const idleSubmitLabel = isCreate
    ? t("finance.charges.form_dialog.submit_create")
    : t("common:actions.save");

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults : defaultsFromItem(props.item));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.item.id]);

  const handleSubmit = async (values: ChargeItemWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ itemId: props.item.id, input: values });
      }
      toast.success(
        isCreate ? t("finance.charges.toasts.added") : t("finance.charges.toasts.updated"),
      );
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
          <DialogTitle>
            {isCreate
              ? t("finance.charges.form_dialog.create_title")
              : t("finance.charges.form_dialog.edit_title")}
          </DialogTitle>
          <DialogDescription>{t("finance.charges.form_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="charge-label">{t("finance.charges.form_dialog.fields.label")}</Label>
            <Input
              id="charge-label"
              autoFocus
              {...form.register("label")}
              aria-invalid={!!form.formState.errors.label}
            />
            {form.formState.errors.label ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.label.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="charge-amount">
                {t("finance.charges.form_dialog.fields.amount")}
              </Label>
              <Input
                id="charge-amount"
                inputMode="decimal"
                placeholder="150.00"
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
              <Label>{t("finance.charges.form_dialog.fields.currency")}</Label>
              {/* Pinned to the booking's currency server-side; shown for clarity. */}
              <p className="text-muted-foreground flex h-9 items-center text-sm">
                {currencyCode ?? "—"}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="charge-notes">{t("finance.charges.form_dialog.fields.notes")}</Label>
            <Textarea id="charge-notes" rows={2} {...form.register("notes")} />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="charge-commissionable"
              checked={commissionable}
              onCheckedChange={(v) => form.setValue("commissionable", v === true)}
            />
            <Label htmlFor="charge-commissionable">
              {t("finance.charges.form_dialog.fields.commissionable")}
            </Label>
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
            <Button type="submit" disabled={submitting}>
              {submitting ? t("common:actions.saving") : idleSubmitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
