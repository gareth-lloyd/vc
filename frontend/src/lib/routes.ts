/** Shared SPA route builders, so features don't hand-roll path literals. */

/** The property detail page accepts either the numeric id or the slug. */
export function propertyDetailsPath(idOrSlug: number | string): string {
  return `/properties/${idOrSlug}/details`;
}
