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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useModifyBookingGuests } from "../hooks";
import { modifyGuestsInputSchema, type BookingDetail, type ModifyGuestsInput } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface ModifyGuestsDialogProps {
  booking: BookingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModifyGuestsDialog({ booking, open, onOpenChange }: ModifyGuestsDialogProps) {
  const { t } = useTranslation("bookings");
  const defaults: ModifyGuestsInput = {
    adults: booking.adults,
    children: booking.children,
    reason: "",
  };
  const form = useForm<ModifyGuestsInput>({
    resolver: zodResolver(modifyGuestsInputSchema),
    defaultValues: defaults,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useModifyBookingGuests(booking.id);

  useEffect(() => {
    if (open) {
      form.reset(defaults);
      setTopLevelError(null);
    }
    // Resetting only on open prevents background refetches from clobbering in-progress edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: ModifyGuestsInput) => {
    setTopLevelError(null);
    const payload: ModifyGuestsInput = {
      adults: values.adults,
      ...(values.children != null ? { children: values.children } : {}),
      ...(values.reason ? { reason: values.reason } : {}),
    };
    try {
      await mutation.mutateAsync(payload);
      toast.success(t("modify_guests_dialog.success_message"));
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
          <DialogTitle>{t("modify_guests_dialog.title")}</DialogTitle>
          <DialogDescription>{t("modify_guests_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="modify-guests-adults">
                {t("modify_guests_dialog.fields.adults")}
              </Label>
              <Input
                id="modify-guests-adults"
                type="number"
                min={1}
                {...form.register("adults", { valueAsNumber: true })}
                aria-invalid={!!form.formState.errors.adults}
              />
              {form.formState.errors.adults ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.adults.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="modify-guests-children">
                {t("modify_guests_dialog.fields.children")}
              </Label>
              <Input
                id="modify-guests-children"
                type="number"
                min={0}
                {...form.register("children", { valueAsNumber: true })}
                aria-invalid={!!form.formState.errors.children}
              />
              {form.formState.errors.children ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.children.message}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="modify-guests-reason">{t("modify_guests_dialog.fields.reason")}</Label>
            <Textarea
              id="modify-guests-reason"
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
                : t("modify_guests_dialog.submit_label")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
