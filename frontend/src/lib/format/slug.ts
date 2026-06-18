/** Derive a URL-safe slug from free text — lowercase, ASCII, dash-separated.
 *
 * Used to pre-fill the create-property slug from the villa name (GAP-049). The
 * server still owns uniqueness; this is a convenience default the operator can
 * override. Mirrors Django's `slugify`: strip diacritics, drop anything that
 * isn't a letter/digit, collapse separators to single dashes, trim the ends.
 */
export function slugify(input: string): string {
  return input
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // drop combining diacritical marks
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-") // any run of non-alphanumerics → one dash
    .replace(/^-+|-+$/g, ""); // trim leading/trailing dashes
}
