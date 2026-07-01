import { differenceInCalendarDays, parseISO } from "date-fns";

export interface BandGeometry {
  leftPct: number;
  widthPct: number;
}

/** A band's rendered edges, in (fractional) day offsets from the window start. */
export interface BandEdges {
  start: number;
  end: number;
}

/**
 * Where a band's edges land on the day axis, before clamping. `halfDayOffset`
 * is the booking treatment: `date_to` is the exclusive checkout date, so the
 * band runs mid-check-in-cell → mid-checkout-cell and back-to-back stays
 * render as kissing bands instead of overlapping.
 */
export function bandEdges(
  dateFrom: string,
  dateTo: string,
  windowStart: Date,
  opts: { halfDayOffset?: boolean } = {},
): BandEdges {
  const offset = opts.halfDayOffset ? 0.5 : 0;
  return {
    start: differenceInCalendarDays(parseISO(dateFrom), windowStart) + offset,
    // Without the offset the exclusive `date_to` is simply the band's end edge.
    end: differenceInCalendarDays(parseISO(dateTo), windowStart) + offset,
  };
}

/**
 * Horizontal placement of a band inside the timeline window, as percentages
 * of the day-grid width. Returns null when the band lies entirely outside.
 */
export function bandGeometry(
  dateFrom: string,
  dateTo: string,
  windowStart: Date,
  dayCount: number,
  opts: { halfDayOffset?: boolean } = {},
): BandGeometry | null {
  const { start, end } = bandEdges(dateFrom, dateTo, windowStart, opts);
  if (end <= 0 || start >= dayCount) return null;
  const clampedStart = Math.max(start, 0);
  const clampedEnd = Math.min(end, dayCount);
  return {
    leftPct: (clampedStart / dayCount) * 100,
    widthPct: ((clampedEnd - clampedStart) / dayCount) * 100,
  };
}

/**
 * Greedy sub-lane assignment for bands sharing a row. Returns the lane index
 * per input band (input order preserved). Operates on *rendered* edges
 * (`bandEdges`), not raw dates, so bookings' half-day shift counts: a hold
 * starting on a booking's checkout day overlaps its last half-cell and
 * stacks, while same-day booking turnover still shares a lane.
 */
export function assignLanes(bands: BandEdges[]): number[] {
  const order = bands
    .map((band, index) => ({ band, index }))
    .sort((a, b) => a.band.start - b.band.start || a.band.end - b.band.end);
  const laneEnds: number[] = [];
  const lanes = new Array<number>(bands.length);
  for (const { band, index } of order) {
    let lane = laneEnds.findIndex((end) => end <= band.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(band.end);
    } else {
      laneEnds[lane] = band.end;
    }
    lanes[index] = lane;
  }
  return lanes;
}
