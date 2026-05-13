import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useConfirmBooking } from "../hooks";
import { isActionAllowedForStatus, type BookingAction } from "../status";
import type { BookingDetail } from "../schemas";
import { CancelBookingDialog } from "./CancelBookingDialog";

interface BookingActionsProps {
  booking: BookingDetail;
}

function disableReason(
  hasRole: boolean,
  action: BookingAction,
  status: BookingDetail["status"],
): string | null {
  if (!hasRole) return "Reservations role required.";
  if (!isActionAllowedForStatus(action, status)) return "Not available for this booking state.";
  return null;
}

export function BookingActions({ booking }: BookingActionsProps) {
  const hasRole = useHasReservationsRole();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const confirmMutation = useConfirmBooking(booking.id);

  const confirmDisableReason = disableReason(hasRole, "confirm", booking.status);
  const cancelDisableReason = disableReason(hasRole, "cancel", booking.status);

  const handleConfirm = async () => {
    try {
      await confirmMutation.mutateAsync();
      toast.success("Booking confirmed");
      setConfirmOpen(false);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Something went wrong";
      toast.error(message);
    }
  };

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        Quick actions
      </p>

      <ActionButton
        label="Confirm booking"
        onClick={() => setConfirmOpen(true)}
        disableReason={confirmDisableReason}
      />
      <ActionButton
        label="Cancel booking"
        onClick={() => setCancelOpen(true)}
        disableReason={cancelDisableReason}
      />

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        onConfirm={handleConfirm}
        title="Confirm this booking?"
        description="The booking will move forward to the next state."
        confirmLabel="Confirm"
        busy={confirmMutation.isPending}
      />

      <CancelBookingDialog bookingId={booking.id} open={cancelOpen} onOpenChange={setCancelOpen} />
    </div>
  );
}

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  disableReason: string | null;
}

function ActionButton({ label, onClick, disableReason }: ActionButtonProps) {
  const button = (
    <Button
      variant="outline"
      size="sm"
      className="w-full justify-start"
      onClick={onClick}
      disabled={disableReason != null}
    >
      {label}
    </Button>
  );

  if (disableReason == null) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block">{button}</span>
      </TooltipTrigger>
      <TooltipContent>{disableReason}</TooltipContent>
    </Tooltip>
  );
}
