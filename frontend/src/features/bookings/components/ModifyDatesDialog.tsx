import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DateRangePicker } from "@/components/form/DateRangePicker";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useModifyBookingDates } from "../hooks";
import { modifyDatesInputSchema, type BookingDetail, type ModifyDatesInput } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface ModifyDatesDialogProps {
  booking: BookingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModifyDatesDialog({ booking, open, onOpenChange }: ModifyDatesDialogProps) {
  const { t } = useTranslation("bookings");
  const defaults: ModifyDatesInput = {
    date_from: booking.date_from,
    date_to: booking.date_to,
    reason: "",
  };
  const form = useForm<ModifyDatesInput>({
    resolver: zodResolver(modifyDatesInputSchema),
    defaultValues: defaults,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useModifyBookingDates(booking.id);

  useEffect(() => {
    if (open) {
      form.reset(defaults);
      setTopLevelError(null);
    }
    // Resetting only on open prevents background refetches from clobbering in-progress edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: ModifyDatesInput) => {
    setTopLevelError(null);
    const payload: ModifyDatesInput = {
      date_from: values.date_from,
      date_to: values.date_to,
      ...(values.reason ? { reason: values.reason } : {}),
    };
    try {
      await mutation.mutateAsync(payload);
      toast.success(t("modify_dates_dialog.success_message"));
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
          <DialogTitle>{t("modify_dates_dialog.title")}</DialogTitle>
          <DialogDescription>{t("modify_dates_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          {/* modifyDatesInputSchema messages are pre-translated at module scope
              (and server text passes through) — pass them raw, no fieldErrorText. */}
          <DateRangePicker
            control={form.control}
            fromName="date_from"
            toName="date_to"
            mode="nights"
            id="modify-dates"
            label={t("modify_dates_dialog.fields.dates")}
            fromLabel={t("modify_dates_dialog.fields.check_in")}
            toLabel={t("modify_dates_dialog.fields.check_out")}
            fromError={form.formState.errors.date_from?.message}
            toError={form.formState.errors.date_to?.message}
          />

          <div className="space-y-2">
            <Label htmlFor="modify-dates-reason">{t("modify_dates_dialog.fields.reason")}</Label>
            <Textarea
              id="modify-dates-reason"
              rows={3}
              {...form.register("reason")}
              aria-invalid={!!form.formState.errors.reason}
            />
            {form.formState.errors.reason ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.reason.message}
              </p>
            ) : null}
          </div>

          <FormErrorAlert message={topLevelError} />

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending
                ? t("common:actions.saving")
                : t("modify_dates_dialog.submit_label")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
