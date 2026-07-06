import { apiGet, apiSend } from "@/lib/api/client";
import {
  propertyDefaultsSchema,
  type PropertyDefaults,
  type PropertyDefaultsWriteInput,
} from "./schemas";

export async function fetchPropertyDefaults(): Promise<PropertyDefaults> {
  const data = await apiGet<unknown>("/property-defaults");
  return propertyDefaultsSchema.parse(data);
}

export async function updatePropertyDefaults(
  body: PropertyDefaultsWriteInput,
): Promise<PropertyDefaults> {
  const data = await apiSend<unknown>("PATCH", "/property-defaults", body);
  return propertyDefaultsSchema.parse(data);
}
