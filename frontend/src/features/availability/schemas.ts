import { z } from "zod";
import { availabilityHoldSchema } from "@/features/properties/schemas";

export { availabilityHoldSchema };
export type { AvailabilityHold } from "@/features/properties/schemas";

export const availabilityBookingBandSchema = z.object({
  id: z.number(),
  property: z.number(),
  date_from: z.string(),
  date_to: z.string(),
  status: z.string(),
  reference: z.string(),
  guest_name: z.string().nullable().optional(),
});
export type AvailabilityBookingBand = z.infer<typeof availabilityBookingBandSchema>;

export const multiAvailabilityResponseSchema = z.object({
  records: z.array(availabilityHoldSchema),
  bookings: z.array(availabilityBookingBandSchema),
});
export type MultiAvailabilityResponse = z.infer<typeof multiAvailabilityResponseSchema>;

export interface TimelineFilters {
  q?: string;
  country?: string;
  region?: string;
  collection?: string;
  min_bedrooms?: number;
  status?: string;
  page?: number;
}

/**
 * The force-filter gate: the timeline fetches nothing until at least one real
 * filter is set. Pagination / window position deliberately don't count.
 */
export function hasAnyFilter(filters: TimelineFilters): boolean {
  return Boolean(
    filters.q ||
    filters.country ||
    filters.region ||
    filters.collection ||
    filters.min_bedrooms ||
    filters.status,
  );
}
