import type { RateCard, RateRule } from "@/features/properties/schemas";

/**
 * The segment-first (Option A) matrix for a single rate card: date segments as
 * rows, occupancy (party-size) bands as columns, one rule per intersection.
 *
 * The legacy model owned occupancy bands as children of a date period, so bands
 * shared their period's dates by construction; the flat `RateRule` lost that
 * (see BUG-013/BUG-014). We reconstruct the grid as a UI convention: rows are
 * the distinct `(date_from, date_to)` pairs, columns the union of
 * `(min_party, max_party)` pairs, and each cell resolves to the rule that
 * matches both — or an empty coordinate.
 *
 * Because columns are the *union* of party bands across all segments, an empty
 * cell can lie under a band sourced from a different segment. Filling it would
 * create a rule overlapping an existing one — which the backend's
 * `raterule_no_overlap` constraint (date range AND party range must both
 * overlap) rejects with a 4xx. So each empty cell carries `fillable`: false when
 * a different rule already covers that (dates × party) region, so the UI can
 * offer "add a price" only where a create would actually succeed.
 */

export interface MatrixBand {
  minParty: number | null;
  maxParty: number | null;
}

export interface MatrixSegment {
  dateFrom: string;
  dateTo: string;
}

export interface MatrixCell {
  /** The rule at this (segment × band) intersection, or null when unfilled. */
  rule: RateRule | null;
  /** Empty cells only: false when another rule already covers this dates×party region. */
  fillable: boolean;
  dateFrom: string;
  dateTo: string;
  minParty: number | null;
  maxParty: number | null;
}

export interface MatrixModel {
  segments: MatrixSegment[];
  bands: MatrixBand[];
  cells: MatrixCell[][];
}

export const segmentKey = (s: { dateFrom: string; dateTo: string }): string =>
  `${s.dateFrom}|${s.dateTo}`;

export const bandKey = (b: MatrixBand): string => `${b.minParty ?? "*"}|${b.maxParty ?? "*"}`;

/** Numeric party-band label ("2–4", "6"), or null when unbounded (let the caller translate). */
export function bandLabel(b: MatrixBand): string | null {
  if (b.minParty == null && b.maxParty == null) return null;
  const min = b.minParty ?? b.maxParty;
  const max = b.maxParty ?? b.minParty;
  return min === max ? `${min}` : `${min}–${max}`;
}

/** Inclusive date-range overlap. */
function datesOverlap(a: { dateFrom: string; dateTo: string }, r: RateRule): boolean {
  return a.dateFrom <= r.date_to && r.date_from <= a.dateTo;
}

/** Party-range overlap, treating null bounds as open (−∞ / +∞) — matches the backend constraint. */
function partiesOverlap(b: MatrixBand, r: RateRule): boolean {
  const bMin = b.minParty ?? -Infinity;
  const bMax = b.maxParty ?? Infinity;
  const rMin = r.min_party ?? -Infinity;
  const rMax = r.max_party ?? Infinity;
  return bMin <= rMax && rMin <= bMax;
}

export function buildMatrix(card: RateCard): MatrixModel {
  const rules = card.rules ?? [];

  const segments: MatrixSegment[] = dedupe(
    rules.map((r) => ({ dateFrom: r.date_from, dateTo: r.date_to })),
    segmentKey,
  ).sort((a, b) => a.dateFrom.localeCompare(b.dateFrom) || a.dateTo.localeCompare(b.dateTo));

  const bands: MatrixBand[] = dedupe(
    rules.map((r) => ({ minParty: r.min_party ?? null, maxParty: r.max_party ?? null })),
    bandKey,
  ).sort((a, b) => (a.minParty ?? 0) - (b.minParty ?? 0) || (a.maxParty ?? 0) - (b.maxParty ?? 0));

  const ruleAt = new Map<string, RateRule>();
  for (const r of rules) {
    ruleAt.set(
      `${segmentKey({ dateFrom: r.date_from, dateTo: r.date_to })}#${bandKey({
        minParty: r.min_party ?? null,
        maxParty: r.max_party ?? null,
      })}`,
      r,
    );
  }

  const cells: MatrixCell[][] = segments.map((s) =>
    bands.map((b) => {
      const rule = ruleAt.get(`${segmentKey(s)}#${bandKey(b)}`) ?? null;
      // An empty cell is fillable only if no OTHER rule already covers this
      // dates×party region (a create there would 4xx on the overlap constraint).
      const fillable = rule
        ? false
        : !rules.some((r) => datesOverlap(s, r) && partiesOverlap(b, r));
      return {
        rule,
        fillable,
        dateFrom: s.dateFrom,
        dateTo: s.dateTo,
        minParty: b.minParty,
        maxParty: b.maxParty,
      };
    }),
  );

  return { segments, bands, cells };
}

function dedupe<T>(items: T[], key: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const k = key(item);
    if (!seen.has(k)) {
      seen.add(k);
      out.push(item);
    }
  }
  return out;
}
