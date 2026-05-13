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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { BookingId } from "@/lib/query/keys";
import { useCancelBooking } from "../hooks";
import { cancelBookingInputSchema, type CancelBookingInput } from "../schemas";

interface CancelBookingDialogProps {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: CancelBookingInput = { reason: "" };

export function CancelBookingDialog({ bookingId, open, onOpenChange }: CancelBookingDialogProps) {
  const form = useForm<CancelBookingInput>({
    resolver: zodResolver(cancelBookingInputSchema),
    defaultValues: DEFAULTS,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useCancelBooking(bookingId);

  useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: CancelBookingInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync(values);
      toast.success("Booking cancelled");
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
          <DialogTitle>Cancel this booking?</DialogTitle>
          <DialogDescription>
            This transitions the booking to cancelled. Add an optional reason for the audit log.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="cancel-reason">Reason (optional)</Label>
            <Textarea
              id="cancel-reason"
              rows={4}
              autoFocus
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
              Keep booking
            </Button>
            <Button type="submit" variant="destructive" disabled={mutation.isPending}>
              {mutation.isPending ? "Cancelling…" : "Cancel booking"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
