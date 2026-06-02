import type { StatTone } from "@/components/data/StatTiles";

/** A balance is overdue once today is past its due date. */
export function isBalanceOverdue(balanceDueAt: string | null | undefined): boolean {
  return balanceDueAt != null && balanceDueAt < new Date().toISOString().slice(0, 10);
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
