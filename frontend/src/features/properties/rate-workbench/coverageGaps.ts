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
}

/**
 * The date ranges a plan does NOT price within the visible window. GAP-110: a
 * plan has no effective window of its own (its periods are the only date
 * authority), so gaps run to the window's edges. Pure date-string arithmetic:
 * ISO dates order lexicographically, and ±1-day steps go through `addDaysIso`.
 * Input periods may be unsorted; overlaps (impossible under the DB EXCLUDE,
 * but cheap to tolerate) merge rather than corrupt the walk.
 */
export function coverageDateGaps(input: CoverageGapsInput): CoverageGap[] {
  // Inclusive last day of the window (the caller's exclusive `to` is the next
  // Jan 1). Defensive: an inverted window yields no gaps rather than one
  // spanning backwards.
  const windowLast = addDaysIso(input.windowTo, -1);
  if (input.windowFrom > windowLast) return [];

  const sorted = [...input.periods].sort((a, b) => a.date_from.localeCompare(b.date_from));
  const gaps: CoverageGap[] = [];
  let cursor = input.windowFrom;
  for (const period of sorted) {
    if (period.date_to < cursor) continue;
    if (period.date_from > windowLast) break;
    if (period.date_from > cursor) {
      gaps.push({ from: cursor, to: addDaysIso(period.date_from, -1) });
    }
    cursor = addDaysIso(period.date_to, 1);
    if (cursor > windowLast) return gaps;
  }
  gaps.push({ from: cursor, to: windowLast });
  return gaps;
}
