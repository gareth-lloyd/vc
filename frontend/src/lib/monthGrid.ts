import { useMemo, useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/**
 * Month-grid state shared by the availability calendars: the viewed month,
 * the week-aligned day window (Monday on/before the 1st through Sunday
 * on/after the last day — exactly the cells the grid draws), and the
 * matching `from`/`to` query strings. Adjacent-month padding days are part
 * of the window, so data fetched with `from`/`to` covers every cell.
 */
export function useMonthGrid() {
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(new Date()));

  const { days, from, to } = useMemo(() => {
    const start = startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 });
    return {
      days: eachDayOfInterval({ start, end }),
      from: format(start, "yyyy-MM-dd"),
      to: format(end, "yyyy-MM-dd"),
    };
  }, [viewMonth]);

  return {
    viewMonth,
    days,
    from,
    to,
    isCurrentMonth: (day: Date) => isSameMonth(day, viewMonth),
    goToPreviousMonth: () => setViewMonth((m) => subMonths(m, 1)),
    goToNextMonth: () => setViewMonth((m) => addMonths(m, 1)),
    goToToday: () => setViewMonth(startOfMonth(new Date())),
  };
}

export function cellsByDate<T extends { date: string }>(cells: T[] | undefined): Map<string, T> {
  const map = new Map<string, T>();
  for (const cell of cells ?? []) map.set(cell.date, cell);
  return map;
}
