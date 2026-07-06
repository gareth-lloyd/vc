import type { Region } from "./schemas";

/**
 * Options for a toolbar region `<Select>`, scoped to a country when one is
 * chosen (case-insensitive iso2 — old bookmarks carry lowercase codes) so the
 * filter never offers an impossible country+region combination. Value is the
 * globally-unique region id as a string; unscoped labels carry the country
 * ISO because names repeat across countries. Callers own the URL-param side:
 * clear the region param whenever the country changes.
 */
export function regionOptionsForCountry(
  regions: Region[],
  countryIso2?: string,
  currentValue?: string,
): Array<{ value: string; label: string }> {
  const iso = countryIso2 ? countryIso2.toUpperCase() : null;
  const rows = iso ? regions.filter((r) => (r.country_iso2 ?? "").toUpperCase() === iso) : regions;
  const options = rows.map((r) => ({
    value: String(r.id),
    label: !iso && r.country_iso2 ? `${r.name} (${r.country_iso2})` : r.name,
  }));
  // A bookmarked URL can carry a region outside the bookmarked country; the
  // active filter must stay visible (and removable) rather than leaving the
  // Select blank while it silently filters the results.
  if (currentValue && !options.some((o) => o.value === currentValue)) {
    const current = regions.find((r) => String(r.id) === currentValue);
    if (current) {
      options.unshift({
        value: currentValue,
        label: current.country_iso2 ? `${current.name} (${current.country_iso2})` : current.name,
      });
    }
  }
  return options;
}
