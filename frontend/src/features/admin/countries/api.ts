import { apiGet, apiSend } from "@/lib/api/client";
import { countrySchema, type Country, type CountryWriteInput } from "./schemas";

// The country LIST read (fetchCountries) moved to lib/geo (GAP-072) — it feeds
// cross-feature dropdowns. The detail fetch and the CRUD mutations stay here:
// editing the country catalog is an admin-only concern.
export async function fetchCountry(iso2: string): Promise<Country> {
  const data = await apiGet<unknown>(`/countries/${iso2}`);
  return countrySchema.parse(data);
}

export async function createCountry(body: CountryWriteInput): Promise<Country> {
  const data = await apiSend<unknown>("POST", "/countries", body);
  return countrySchema.parse(data);
}

export async function updateCountry(
  iso2: string,
  body: Partial<CountryWriteInput>,
): Promise<Country> {
  const data = await apiSend<unknown>("PATCH", `/countries/${iso2}`, body);
  return countrySchema.parse(data);
}

export async function deleteCountry(iso2: string): Promise<void> {
  await apiSend<void>("DELETE", `/countries/${iso2}`);
}
