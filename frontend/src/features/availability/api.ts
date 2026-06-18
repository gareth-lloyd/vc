import { apiGet } from "@/lib/api/client";
import {
  multiAvailabilityResponseSchema,
  weeklyPricesResponseSchema,
  type MultiAvailabilityResponse,
  type WeeklyPricesResponse,
} from "./schemas";

export async function fetchMultiAvailability(
  propertyIds: number[],
  from: string,
  to: string,
): Promise<MultiAvailabilityResponse> {
  const data = await apiGet<unknown>("/availability", {
    query: { property_ids: propertyIds.join(","), from, to },
  });
  return multiAvailabilityResponseSchema.parse(data);
}

export async function fetchWeeklyPrices(
  propertyIds: number[],
  from: string,
  to: string,
): Promise<WeeklyPricesResponse> {
  const data = await apiGet<unknown>("/availability/weekly-prices", {
    query: { property_ids: propertyIds.join(","), from, to },
  });
  return weeklyPricesResponseSchema.parse(data);
}
