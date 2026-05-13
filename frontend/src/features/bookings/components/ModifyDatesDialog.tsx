import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { useModifyBookingDates } from "../hooks";
import { modifyDatesInputSchema, type BookingDetail, type ModifyDatesInput } from "../schemas";

interface ModifyDatesDialogProps {
  booking: BookingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModifyDatesDialog({ booking, open, onOpenChange }: ModifyDatesDialogProps) {
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
      toast.success("Dates updated");
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error("Something went wrong");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Modify dates</DialogTitle>
          <DialogDescription>
            Adjust check-in and check-out. Pricing may need to be recalculated separately.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="modify-date-from">Check-in</Label>
              <Input
                id="modify-date-from"
                type="date"
                {...form.register("date_from")}
                aria-invalid={!!form.formState.errors.date_from}
              />
              {form.formState.errors.date_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.date_from.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="modify-date-to">Check-out</Label>
              <Input
                id="modify-date-to"
                type="date"
                {...form.register("date_to")}
                aria-invalid={!!form.formState.errors.date_to}
              />
              {form.formState.errors.date_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.date_to.message}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="modify-dates-reason">Reason (optional)</Label>
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

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save dates"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
