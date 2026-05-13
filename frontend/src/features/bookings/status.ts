import type { BookingDetail, BookingStatus } from "./schemas";

export type BookingAction =
  | "confirm"
  | "cancel"
  | "owner_decline"
  | "modify_dates"
  | "modify_guests"
  | "archive"
  | "restore"
  | "check_in"
  | "check_out"
  | "resend_confirmation";

const FROM_STATUS: Record<
  Exclude<BookingAction, "archive" | "restore">,
  ReadonlySet<BookingStatus>
> = {
  confirm: new Set(["draft", "pending_owner_approval"]),
  cancel: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
  ]),
  owner_decline: new Set(["pending_owner_approval"]),
  modify_dates: new Set(["awaiting_deposit", "deposit_paid", "awaiting_balance", "balance_paid"]),
  modify_guests: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
  ]),
  check_in: new Set(["balance_paid"]),
  check_out: new Set(["checked_in"]),
  resend_confirmation: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
    "checked_in",
  ]),
};

const TERMINAL_STATUSES: ReadonlySet<BookingStatus> = new Set([
  "checked_out",
  "cancelled",
  "expired",
  "declined",
]);

export function isActionAvailable(action: BookingAction, booking: BookingDetail): boolean {
  if (action === "archive") return !booking.is_archived && TERMINAL_STATUSES.has(booking.status);
  if (action === "restore") return !!booking.is_archived;
  return FROM_STATUS[action].has(booking.status);
}
