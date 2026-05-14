import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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

const PRIMARY_ACTION_KEYS: ReadonlyArray<{ action: BookingAction; labelKey: string }> = [
  { action: "confirm", labelKey: "actions.confirm_booking" },
  { action: "owner_decline", labelKey: "actions.owner_decline" },
  { action: "cancel", labelKey: "actions.cancel_booking" },
  { action: "check_in", labelKey: "actions.check_in" },
  { action: "check_out", labelKey: "actions.check_out" },
];

const SECONDARY_ACTION_KEYS: ReadonlyArray<{ action: BookingAction; labelKey: string }> = [
  { action: "modify_dates", labelKey: "actions.modify_dates" },
  { action: "modify_guests", labelKey: "actions.modify_guests" },
  { action: "resend_confirmation", labelKey: "actions.resend_confirmation" },
  { action: "archive", labelKey: "actions.archive_booking" },
  { action: "restore", labelKey: "actions.restore_booking" },
];

interface ConfirmConfig {
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  successMessage: string;
}

export function BookingActions({ booking }: BookingActionsProps) {
  const { t } = useTranslation("bookings");
  const hasRole = useHasReservationsRole();
  const [activeDialog, setActiveDialog] = useState<BookingAction | null>(null);

  const disableReason = (action: BookingAction): string | null => {
    if (!hasRole) return t("common:errors.reservations_role_required");
    if (!isActionAvailable(action, booking)) return t("errors.not_available_for_state");
    return null;
  };

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
        title: t("confirm.confirm.title"),
        description: t("confirm.confirm.description"),
        confirmLabel: t("common:actions.confirm"),
        successMessage: t("confirm.confirm.success_message"),
      },
      mutation: confirmMutation,
    },
    archive: {
      config: {
        title: t("confirm.archive.title"),
        description: t("confirm.archive.description"),
        confirmLabel: t("confirm.archive.confirm_label"),
        successMessage: t("confirm.archive.success_message"),
      },
      mutation: archiveMutation,
    },
    restore: {
      config: {
        title: t("confirm.restore.title"),
        description: t("confirm.restore.description"),
        confirmLabel: t("confirm.restore.confirm_label"),
        successMessage: t("confirm.restore.success_message"),
      },
      mutation: restoreMutation,
    },
    check_in: {
      config: {
        title: t("confirm.check_in.title"),
        description: t("confirm.check_in.description"),
        confirmLabel: t("confirm.check_in.confirm_label"),
        successMessage: t("confirm.check_in.success_message"),
      },
      mutation: checkInMutation,
    },
    check_out: {
      config: {
        title: t("confirm.check_out.title"),
        description: t("confirm.check_out.description"),
        confirmLabel: t("confirm.check_out.confirm_label"),
        successMessage: t("confirm.check_out.success_message"),
      },
      mutation: checkOutMutation,
    },
    resend_confirmation: {
      config: {
        title: t("confirm.resend_confirmation.title"),
        description: t("confirm.resend_confirmation.description"),
        confirmLabel: t("confirm.resend_confirmation.confirm_label"),
        successMessage: t("confirm.resend_confirmation.success_message"),
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
      const message = error instanceof ApiError ? error.detail : t("common:errors.generic");
      toast.error(message);
    }
  };

  const primaryActions = useMemo(
    () => PRIMARY_ACTION_KEYS.map(({ action, labelKey }) => ({ action, label: t(labelKey) })),
    [t],
  );
  const secondaryActions = useMemo(
    () => SECONDARY_ACTION_KEYS.map(({ action, labelKey }) => ({ action, label: t(labelKey) })),
    [t],
  );

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        {t("actions.quick_actions")}
      </p>

      {primaryActions.map(({ action, label }) => (
        <ActionButton
          key={action}
          label={label}
          onClick={() => setActiveDialog(action)}
          disableReason={disableReason(action)}
        />
      ))}

      <SecondaryActionsMenu
        actions={secondaryActions}
        booking={booking}
        hasRole={hasRole}
        moreLabel={t("actions.more_actions")}
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
  actions: ReadonlyArray<{ action: BookingAction; label: string }>;
  booking: BookingDetail;
  hasRole: boolean;
  moreLabel: string;
  onSelect: (action: BookingAction) => void;
}

function SecondaryActionsMenu({
  actions,
  booking,
  hasRole,
  moreLabel,
  onSelect,
}: SecondaryActionsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="w-full justify-between" disabled={!hasRole}>
          {moreLabel}
          <ChevronDown className="ml-2 size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-(--radix-dropdown-menu-trigger-width)">
        {actions.map(({ action, label }) => (
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
