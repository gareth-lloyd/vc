import { addDaysIso } from "@/lib/format/date";

/** An unpriced date range, both ends inclusive — dialog-prefill-ready. */
export interface CoverageGap {
  from: string;
  to: string;
}

export interface CoverageGapsInput {
  /** The plan's periods (inclusive `date_from`/`date_to`). ALL periods count
   * as coverage, active or not: the DB overlap EXCLUDE spans inactive rows,
   * so a "gap" overlapping one would 400 on create. */
  periods: readonly { date_from: string; date_to: string }[];
  /** Inclusive window start (yearWindow `from`). */
  windowFrom: string;
  /** EXCLUSIVE window end (yearWindow `to`, the next Jan 1). */
  windowTo: string;
  /** Plan effective range (inclusive, nullable) — gaps are clamped inside it. */
  effectiveFrom?: string | null;
  effectiveTo?: string | null;
}

/**
 * The date ranges a plan does NOT price within the visible window, clamped to
 * its effective range. Pure date-string arithmetic: ISO dates order
 * lexicographically, and ±1-day steps go through `addDaysIso`. Input periods
 * may be unsorted; overlaps (impossible under the DB EXCLUDE, but cheap to
 * tolerate) merge rather than corrupt the walk.
 */
export function coverageDateGaps(input: CoverageGapsInput): CoverageGap[] {
  const lo =
    input.effectiveFrom && input.effectiveFrom > input.windowFrom
      ? input.effectiveFrom
      : input.windowFrom;
  const windowLast = addDaysIso(input.windowTo, -1);
  const hi = input.effectiveTo && input.effectiveTo < windowLast ? input.effectiveTo : windowLast;
  if (lo > hi) return [];

  const sorted = [...input.periods].sort((a, b) => a.date_from.localeCompare(b.date_from));
  const gaps: CoverageGap[] = [];
  let cursor = lo;
  for (const period of sorted) {
    if (period.date_to < cursor) continue;
    if (period.date_from > hi) break;
    if (period.date_from > cursor) {
      gaps.push({ from: cursor, to: addDaysIso(period.date_from, -1) });
    }
    cursor = addDaysIso(period.date_to, 1);
    if (cursor > hi) return gaps;
  }
  gaps.push({ from: cursor, to: hi });
  return gaps;
}
