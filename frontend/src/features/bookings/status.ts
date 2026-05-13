import type { BookingStatus } from "./schemas";

export type BookingAction = "confirm" | "cancel";

const CONFIRM_FROM = new Set<BookingStatus>(["draft", "pending_owner_approval"]);

const CANCEL_FROM = new Set<BookingStatus>([
  "draft",
  "pending_owner_approval",
  "awaiting_deposit",
  "deposit_paid",
  "awaiting_balance",
  "balance_paid",
]);

export function isActionAllowedForStatus(action: BookingAction, status: BookingStatus): boolean {
  if (action === "confirm") return CONFIRM_FROM.has(status);
  if (action === "cancel") return CANCEL_FROM.has(status);
  return false;
}
