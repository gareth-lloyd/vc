import type { RatePeriod, RateBand } from "@/features/properties/schemas";

/**
 * The segment-first matrix for a plan: rate periods as rows (each owns one
 * inclusive date range), occupancy (party-size) bands as columns, one rule per
 * intersection.
 *
 * GAP-056 made the grid honest: a `RatePeriod` owns the dates, and its
 * `RateBand` children are pure party bands that inherit them. So rows are the
 * plan's periods and columns are the union of `(min_party, max_party)` pairs
 * across every period's bands; each cell resolves to the band in that period
 * matching the column, or an empty coordinate.
 *
 * Within one period every band shares the period's dates, so an empty cell is
 * fillable unless another band in the *same* period already covers that party
 * range (a create there would 4xx on the per-period bands-disjoint constraint).
 * Columns are the union across periods, so a period legitimately has no band in
 * some columns — those are the fillable coordinates.
 */

export interface MatrixBand {
  minParty: number | null;
  maxParty: number | null;
}

export interface MatrixSegment {
  periodId: number;
  name: string;
  dateFrom: string;
  dateTo: string;
}

export interface MatrixCell {
  /** The band at this (period × column) intersection, or null when unfilled. */
  band: RateBand | null;
  /** Empty cells only: false when another band in this period already covers this party range. */
  fillable: boolean;
  /** The period this cell belongs to — the create target for a fill. */
  periodId: number;
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

export const bandKey = (b: MatrixBand): string => `${b.minParty ?? "*"}|${b.maxParty ?? "*"}`;

/** Numeric party-band label ("2–4", "6"), or null when unbounded (let the caller translate). */
export function bandLabel(b: MatrixBand): string | null {
  if (b.minParty == null && b.maxParty == null) return null;
  const min = b.minParty ?? b.maxParty;
  const max = b.maxParty ?? b.minParty;
  return min === max ? `${min}` : `${min}–${max}`;
}

/** Party-range overlap, treating null bounds as open (−∞ / +∞) — matches the backend constraint. */
function partiesOverlap(b: MatrixBand, r: RateBand): boolean {
  const bMin = b.minParty ?? -Infinity;
  const bMax = b.maxParty ?? Infinity;
  const rMin = r.min_party ?? -Infinity;
  const rMax = r.max_party ?? Infinity;
  return bMin <= rMax && rMin <= bMax;
}

export function buildMatrix(periods: RatePeriod[]): MatrixModel {
  const segments: MatrixSegment[] = periods
    .map((p) => ({
      periodId: p.id,
      name: p.name ?? "",
      dateFrom: p.date_from,
      dateTo: p.date_to,
    }))
    .sort((a, b) => a.dateFrom.localeCompare(b.dateFrom) || a.dateTo.localeCompare(b.dateTo));

  const bands: MatrixBand[] = dedupe(
    periods.flatMap((p) =>
      (p.bands ?? []).map((r) => ({
        minParty: r.min_party ?? null,
        maxParty: r.max_party ?? null,
      })),
    ),
    bandKey,
  ).sort((a, b) => (a.minParty ?? 0) - (b.minParty ?? 0) || (a.maxParty ?? 0) - (b.maxParty ?? 0));

  const bandsByPeriod = new Map<number, RateBand[]>();
  const bandAt = new Map<string, RateBand>();
  for (const p of periods) {
    const periodBands = p.bands ?? [];
    bandsByPeriod.set(p.id, periodBands);
    for (const r of periodBands) {
      bandAt.set(
        `${p.id}#${bandKey({ minParty: r.min_party ?? null, maxParty: r.max_party ?? null })}`,
        r,
      );
    }
  }

  const cells: MatrixCell[][] = segments.map((s) =>
    bands.map((b) => {
      const band = bandAt.get(`${s.periodId}#${bandKey(b)}`) ?? null;
      // Empty cell is fillable unless another band in THIS period covers the
      // party range (same period ⇒ same dates, so only party matters).
      const fillable = band
        ? false
        : !(bandsByPeriod.get(s.periodId) ?? []).some((r) => partiesOverlap(b, r));
      return {
        band,
        fillable,
        periodId: s.periodId,
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
