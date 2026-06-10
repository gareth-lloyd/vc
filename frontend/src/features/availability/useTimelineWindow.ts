import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { addDays, eachDayOfInterval, format, isValid, parseISO, startOfWeek } from "date-fns";

export const TIMELINE_WINDOW_DAYS = 35;

const toMonday = (date: Date) => startOfWeek(date, { weekStartsOn: 1 });

/**
 * The timeline's visible window: a Monday-aligned 35-day span driven by the
 * `start` URL param (bookmarkable, unlike the single-villa tab's local
 * month state). `to` is exclusive, matching the API's overlap predicate.
 */
export function useTimelineWindow() {
  const [params, setParams] = useSearchParams();
  const startParam = params.get("start");

  const start = useMemo(() => {
    if (startParam) {
      const parsed = parseISO(startParam);
      if (isValid(parsed)) return toMonday(parsed);
    }
    return toMonday(new Date());
  }, [startParam]);

  const { days, from, to } = useMemo(
    () => ({
      days: eachDayOfInterval({ start, end: addDays(start, TIMELINE_WINDOW_DAYS - 1) }),
      from: format(start, "yyyy-MM-dd"),
      to: format(addDays(start, TIMELINE_WINDOW_DAYS), "yyyy-MM-dd"),
    }),
    [start],
  );

  const setStart = (next: Date | null) => {
    setParams(
      (prev) => {
        const updated = new URLSearchParams(prev);
        if (next) updated.set("start", format(next, "yyyy-MM-dd"));
        else updated.delete("start");
        return updated;
      },
      { replace: true },
    );
  };

  return {
    start,
    days,
    from,
    to,
    goPrev: () => setStart(addDays(start, -7)),
    goNext: () => setStart(addDays(start, 7)),
    goToday: () => setStart(null),
  };
}
