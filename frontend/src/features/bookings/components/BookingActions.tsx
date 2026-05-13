import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useArchiveBooking,
  useCheckInBooking,
  useCheckOutBooking,
  useConfirmBooking,
  useResendBookingConfirmation,
  useRestoreBooking,
} from "../hooks";
import { isActionAvailable, type BookingAction } from "../status";
import type { BookingDetail } from "../schemas";
import { CancelBookingDialog } from "./CancelBookingDialog";
import { DeclineBookingDialog } from "./DeclineBookingDialog";
import { ModifyDatesDialog } from "./ModifyDatesDialog";
import { ModifyGuestsDialog } from "./ModifyGuestsDialog";

interface BookingActionsProps {
  booking: BookingDetail;
}

const PRIMARY_ACTIONS: ReadonlyArray<{ action: BookingAction; label: string }> = [
  { action: "confirm", label: "Confirm booking" },
  { action: "owner_decline", label: "Owner decline" },
  { action: "cancel", label: "Cancel booking" },
  { action: "check_in", label: "Check in" },
  { action: "check_out", label: "Check out" },
];

const SECONDARY_ACTIONS: ReadonlyArray<{ action: BookingAction; label: string }> = [
  { action: "modify_dates", label: "Modify dates" },
  { action: "modify_guests", label: "Modify guests" },
  { action: "resend_confirmation", label: "Resend confirmation" },
  { action: "archive", label: "Archive booking" },
  { action: "restore", label: "Restore booking" },
];

interface ConfirmConfig {
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  successMessage: string;
}

function disableReason(
  hasRole: boolean,
  action: BookingAction,
  booking: BookingDetail,
): string | null {
  if (!hasRole) return "Reservations role required.";
  if (!isActionAvailable(action, booking)) return "Not available for this booking state.";
  return null;
}

export function BookingActions({ booking }: BookingActionsProps) {
  const hasRole = useHasReservationsRole();
  const [activeDialog, setActiveDialog] = useState<BookingAction | null>(null);

  const confirmMutation = useConfirmBooking(booking.id);
  const archiveMutation = useArchiveBooking(booking.id);
  const restoreMutation = useRestoreBooking(booking.id);
  const checkInMutation = useCheckInBooking(booking.id);
  const checkOutMutation = useCheckOutBooking(booking.id);
  const resendMutation = useResendBookingConfirmation(booking.id);

  const closeDialog = () => setActiveDialog(null);
  const handleDialogOpenChange = (open: boolean) => {
    if (!open) closeDialog();
  };

  const confirmActions: Partial<
    Record<
      BookingAction,
      {
        config: ConfirmConfig;
        mutation: { mutateAsync: () => Promise<unknown>; isPending: boolean };
      }
    >
  > = {
    confirm: {
      config: {
        title: "Confirm this booking?",
        description: "The booking will move forward to the next state.",
        confirmLabel: "Confirm",
        successMessage: "Booking confirmed",
      },
      mutation: confirmMutation,
    },
    archive: {
      config: {
        title: "Archive this booking?",
        description: "It will be hidden from default lists. You can restore it later.",
        confirmLabel: "Archive",
        successMessage: "Booking archived",
      },
      mutation: archiveMutation,
    },
    restore: {
      config: {
        title: "Restore this booking?",
        description: "It will reappear in default lists.",
        confirmLabel: "Restore",
        successMessage: "Booking restored",
      },
      mutation: restoreMutation,
    },
    check_in: {
      config: {
        title: "Check in?",
        description: "Mark the guest as checked in.",
        confirmLabel: "Check in",
        successMessage: "Guest checked in",
      },
      mutation: checkInMutation,
    },
    check_out: {
      config: {
        title: "Check out?",
        description: "Mark the guest as checked out.",
        confirmLabel: "Check out",
        successMessage: "Guest checked out",
      },
      mutation: checkOutMutation,
    },
    resend_confirmation: {
      config: {
        title: "Resend confirmation email?",
        description: "The guest will receive the booking confirmation again.",
        confirmLabel: "Resend",
        successMessage: "Confirmation resent",
      },
      mutation: resendMutation,
    },
  };

  const activeConfirm = activeDialog ? confirmActions[activeDialog] : undefined;

  const handleConfirmAction = async () => {
    if (!activeConfirm) return;
    try {
      await activeConfirm.mutation.mutateAsync();
      toast.success(activeConfirm.config.successMessage);
      closeDialog();
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

      {PRIMARY_ACTIONS.map(({ action, label }) => (
        <ActionButton
          key={action}
          label={label}
          onClick={() => setActiveDialog(action)}
          disableReason={disableReason(hasRole, action, booking)}
        />
      ))}

      <SecondaryActionsMenu
        booking={booking}
        hasRole={hasRole}
        onSelect={(action) => setActiveDialog(action)}
      />

      {activeConfirm ? (
        <ConfirmDialog
          open={activeDialog != null}
          onOpenChange={handleDialogOpenChange}
          onConfirm={handleConfirmAction}
          title={activeConfirm.config.title}
          description={activeConfirm.config.description}
          confirmLabel={activeConfirm.config.confirmLabel}
          destructive={activeConfirm.config.destructive}
          busy={activeConfirm.mutation.isPending}
        />
      ) : null}

      <CancelBookingDialog
        bookingId={booking.id}
        open={activeDialog === "cancel"}
        onOpenChange={handleDialogOpenChange}
      />

      <DeclineBookingDialog
        bookingId={booking.id}
        open={activeDialog === "owner_decline"}
        onOpenChange={handleDialogOpenChange}
      />

      <ModifyDatesDialog
        booking={booking}
        open={activeDialog === "modify_dates"}
        onOpenChange={handleDialogOpenChange}
      />

      <ModifyGuestsDialog
        booking={booking}
        open={activeDialog === "modify_guests"}
        onOpenChange={handleDialogOpenChange}
      />
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

interface SecondaryActionsMenuProps {
  booking: BookingDetail;
  hasRole: boolean;
  onSelect: (action: BookingAction) => void;
}

function SecondaryActionsMenu({ booking, hasRole, onSelect }: SecondaryActionsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="w-full justify-between" disabled={!hasRole}>
          More actions
          <ChevronDown className="ml-2 size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-(--radix-dropdown-menu-trigger-width)">
        {SECONDARY_ACTIONS.map(({ action, label }) => (
          <DropdownMenuItem
            key={action}
            disabled={!isActionAvailable(action, booking)}
            onSelect={(event) => {
              event.preventDefault();
              onSelect(action);
            }}
          >
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
