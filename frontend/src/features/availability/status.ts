import { reasonClasses } from "@/features/properties/availabilityTokens";

/**
 * v1 display vocabulary for timeline bands. BOOKED_VC is deliberately absent:
 * legacy-migrated bookings all default `site_source=main_website`, so a
 * Booked / Booked-VC split would mislabel the whole historical portfolio.
 * Reintroduce when a trustworthy booking-origin signal exists.
 */
export type BandDisplayStatus = "booked" | "on_hold" | "stop_sale";

const STOP_SALE_REASONS = new Set(["owner_block", "maintenance"]);

export function holdDisplayStatus(reason: string): BandDisplayStatus {
  return STOP_SALE_REASONS.has(reason) ? "stop_sale" : "on_hold";
}

// Representative reason per display status — colours come from the shared
// token map so this screen tracks the single-villa calendar.
const STATUS_REASON: Record<BandDisplayStatus, string> = {
  booked: "booked",
  stop_sale: "owner_block",
  on_hold: "quotation",
};

export function bandStatusClasses(status: BandDisplayStatus): string {
  return reasonClasses(STATUS_REASON[status]);
}
