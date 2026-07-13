import type { StatTone } from "@/components/data/StatTiles";
import { todayIso } from "@/lib/format/date";
import { parseMoney } from "@/lib/format/money";

/**
 * The Total / Paid / Due trio for a booking — single source for the rail
 * tiles, the Overview tiles, and the list finance column.
 *
 * `total` is the guest-facing gross from the backend's `booking_total()`
 * money authority (snapshot-first plus charge items, SMELL-020) — it can
 * legitimately differ from the bare `balance_due` column, which is only the
 * client-side fallback when `total` is absent.
 * `paid` comes from the backend's settled-payments sum and is never derived by
 * subtraction: `total − balance_due` used to surface the agency commission as
 * a negative "Paid" on net-priced bookings.
 */
export function bookingFinance(booking: {
  total?: string | null;
  balance_due: string;
  amount_paid?: string | null;
}): { total: number; paid: number; due: number } {
  const total = parseMoney(booking.total ?? booking.balance_due);
  const paid = parseMoney(booking.amount_paid ?? "0");
  return { total, paid, due: total - paid };
}

/** A balance is overdue once today is past its due date. */
export function isBalanceOverdue(balanceDueAt: string | null | undefined): boolean {
  return balanceDueAt != null && balanceDueAt < todayIso();
}

/**
 * Tone for a "Due" amount: muted when nothing is owed, danger once the balance
 * is overdue, warning while it is still outstanding but in date. Single source
 * for the rail tile, the Overview tile, and the list finance column.
 */
export function dueTone(outstanding: number, balanceDueAt: string | null | undefined): StatTone {
  if (!(outstanding > 0)) return "muted";
  return isBalanceOverdue(balanceDueAt) ? "danger" : "warning";
}
