/**
 * Reason → token-class map shared by the single-villa availability calendar
 * (`tabs/AvailabilityTab.tsx`) and the multi-villa timeline
 * (`features/availability`). One source of truth so the two screens' colours
 * and legends cannot drift.
 */
const REASON_TOKEN_CLASSES: Record<string, string> = {
  booked: "bg-primary text-primary-foreground font-medium",
  quotation: "bg-warning/25 text-warning",
  owner_block: "bg-hold/35 text-hold",
  maintenance: "bg-status-neutral/35 text-status-neutral",
  manual: "bg-info/30 text-info",
};

export function reasonClasses(reason: string): string {
  return REASON_TOKEN_CLASSES[reason] ?? "text-foreground";
}
