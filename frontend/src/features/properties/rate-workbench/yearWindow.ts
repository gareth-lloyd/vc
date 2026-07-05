import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { differenceInCalendarDays, format } from "date-fns";

/**
 * The rate workbench's timeline window is a whole calendar year — unlike the
 * availability tab's 35-day Monday window. `windowStart` is Jan 1 (local
 * midnight, matching `parseISO` of a `yyyy-MM-dd` band date), `to` is the
 * exclusive Jan 1 of the next year, and `dayCount` is 365 or 366.
 */
export interface YearWindow {
  year: number;
  windowStart: Date;
  dayCount: number;
  from: string;
  to: string;
}

export function yearWindowFor(year: number): YearWindow {
  const windowStart = new Date(year, 0, 1);
  const nextYearStart = new Date(year + 1, 0, 1);
  return {
    year,
    windowStart,
    dayCount: differenceInCalendarDays(nextYearStart, windowStart),
    from: format(windowStart, "yyyy-MM-dd"),
    to: format(nextYearStart, "yyyy-MM-dd"),
  };
}

/** One month gridline/label, positioned as a percentage of the year width. */
export interface MonthTick {
  key: string;
  /** First of the month, for locale-aware formatting at render. */
  date: Date;
  leftPct: number;
}

export function monthTicks(windowStart: Date, dayCount: number): MonthTick[] {
  const year = windowStart.getFullYear();
  return Array.from({ length: 12 }, (_, month) => {
    const first = new Date(year, month, 1);
    return {
      key: format(first, "yyyy-MM"),
      date: first,
      leftPct: (differenceInCalendarDays(first, windowStart) / dayCount) * 100,
    };
  });
}

const MIN_YEAR = 2000;
const MAX_YEAR = 2100;

/**
 * Reads the selected year from the `?year=` search param (bookmarkable), falling
 * back to the current calendar year. Mirrors `useTimelineWindow`'s URL-driven
 * approach so a workbench view can be linked and shared.
 */
export function useYearWindow() {
  const [params, setParams] = useSearchParams();
  const yearParam = params.get("year");

  const year = useMemo(() => {
    const parsed = yearParam ? Number(yearParam) : NaN;
    if (Number.isInteger(parsed) && parsed >= MIN_YEAR && parsed <= MAX_YEAR) {
      return parsed;
    }
    return new Date().getFullYear();
  }, [yearParam]);

  const window = useMemo(() => yearWindowFor(year), [year]);

  const setYear = (next: number) => {
    setParams(
      (prev) => {
        const updated = new URLSearchParams(prev);
        updated.set("year", String(next));
        return updated;
      },
      { replace: true },
    );
  };

  return {
    ...window,
    setYear,
    goPrev: () => setYear(year - 1),
    goNext: () => setYear(year + 1),
  };
}
