import { apiGet } from "@/lib/api/client";
import { multiAvailabilityResponseSchema, type MultiAvailabilityResponse } from "./schemas";

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
