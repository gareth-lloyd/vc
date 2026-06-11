import type { AvailabilityBookingBand, AvailabilityHold } from "./schemas";

export type TimelineBand =
  | { kind: "booking"; booking: AvailabilityBookingBand }
  | { kind: "hold"; hold: AvailabilityHold };

export function bandDates(band: TimelineBand): { date_from: string; date_to: string } {
  return band.kind === "booking" ? band.booking : band.hold;
}
