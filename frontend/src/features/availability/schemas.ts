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

// GAP-030 — weekly guide pricing on the timeline. `price` is a decimal string
// (or null when incomplete/POA); `is_projected` flags a guide vs a firm price.
export const weeklyPriceSchema = z.object({
  week_start: z.string(),
  week_end: z.string(),
  price: z.string().nullable(),
  currency_code: z.string().nullable(),
  is_projected: z.boolean(),
  is_poa: z.boolean(),
  error_code: z.string().nullable(),
});
export type WeeklyPrice = z.infer<typeof weeklyPriceSchema>;

export const weeklyPricesPropertySchema = z.object({
  property_id: z.number(),
  // The changeover-day code ("sat") for a fixed-changeover villa, or null when
  // flexible/ANY (deferred — no price strip).
  changeover_day: z.string().nullable(),
  weeks: z.array(weeklyPriceSchema),
});
export type WeeklyPricesProperty = z.infer<typeof weeklyPricesPropertySchema>;

export const weeklyPricesResponseSchema = z.object({
  properties: z.array(weeklyPricesPropertySchema),
});
export type WeeklyPricesResponse = z.infer<typeof weeklyPricesResponseSchema>;

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
