/** Shared SPA route builders, so features don't hand-roll path literals. */

/** The property detail page accepts either the numeric id or the slug. */
export function propertyDetailsPath(idOrSlug: number | string): string {
  return `/properties/${idOrSlug}/details`;
}

/** The single-villa availability calendar tab. */
export function propertyAvailabilityPath(idOrSlug: number | string): string {
  return `/properties/${idOrSlug}/availability`;
}
