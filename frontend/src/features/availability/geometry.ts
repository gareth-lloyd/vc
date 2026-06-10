import { differenceInCalendarDays, parseISO } from "date-fns";

export interface BandGeometry {
  leftPct: number;
  widthPct: number;
}

/**
 * Horizontal placement of a band inside the timeline window, as percentages
 * of the day-grid width. Returns null when the band lies entirely outside.
 *
 * `halfDayOffset` is the booking treatment: `date_to` is the exclusive
 * checkout date, so the band runs mid-check-in-cell → mid-checkout-cell and
 * back-to-back stays render as kissing bands instead of overlapping.
 */
export function bandGeometry(
  dateFrom: string,
  dateTo: string,
  windowStart: Date,
  dayCount: number,
  opts: { halfDayOffset?: boolean } = {},
): BandGeometry | null {
  const offset = opts.halfDayOffset ? 0.5 : 0;
  const start = differenceInCalendarDays(parseISO(dateFrom), windowStart) + offset;
  // Without the offset the exclusive `date_to` is simply the band's end edge.
  const end = differenceInCalendarDays(parseISO(dateTo), windowStart) + offset;
  if (end <= 0 || start >= dayCount) return null;
  const clampedStart = Math.max(start, 0);
  const clampedEnd = Math.min(end, dayCount);
  return {
    leftPct: (clampedStart / dayCount) * 100,
    widthPct: ((clampedEnd - clampedStart) / dayCount) * 100,
  };
}

interface DateRange {
  date_from: string;
  date_to: string;
}

/**
 * Greedy sub-lane assignment for bands sharing a villa row. Returns the lane
 * index per input band (input order preserved). `date_to` is exclusive, so
 * same-day turnover shares a lane; only genuine overlaps stack.
 */
export function assignLanes(bands: DateRange[]): number[] {
  const order = bands
    .map((band, index) => ({ band, index }))
    .sort(
      (a, b) =>
        a.band.date_from.localeCompare(b.band.date_from) ||
        a.band.date_to.localeCompare(b.band.date_to),
    );
  const laneEnds: string[] = [];
  const lanes = new Array<number>(bands.length);
  for (const { band, index } of order) {
    let lane = laneEnds.findIndex((end) => end <= band.date_from);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(band.date_to);
    } else {
      laneEnds[lane] = band.date_to;
    }
    lanes[index] = lane;
  }
  return lanes;
}
