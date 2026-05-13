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
import { useModifyBookingGuests } from "../hooks";
import { modifyGuestsInputSchema, type BookingDetail, type ModifyGuestsInput } from "../schemas";

interface ModifyGuestsDialogProps {
  booking: BookingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModifyGuestsDialog({ booking, open, onOpenChange }: ModifyGuestsDialogProps) {
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
      toast.success("Party size updated");
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
          <DialogTitle>Modify guests</DialogTitle>
          <DialogDescription>Adjust the number of adults and children.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="modify-guests-adults">Adults</Label>
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
              <Label htmlFor="modify-guests-children">Children</Label>
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
            <Label htmlFor="modify-guests-reason">Reason (optional)</Label>
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
              {mutation.isPending ? "Saving…" : "Save guests"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
