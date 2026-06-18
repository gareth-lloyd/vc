import { format, type Locale } from "date-fns";
import type { TFunction } from "i18next";

/**
 * Header label for the timeline window's spanning month(s): "June 2026" in a
 * single month, "June – July 2026" across a month boundary, "December 2025 –
 * January 2026" across a year boundary. Month/year text comes from date-fns in
 * the active locale; the dash join is an i18n key (never a concatenated
 * literal). `start`/`end` are the window's first and last days.
 */
export function monthSpanLabel(
  start: Date,
  end: Date,
  t: TFunction<"availability">,
  locale: Locale,
): string {
  const sameYear = start.getFullYear() === end.getFullYear();
  if (sameYear && start.getMonth() === end.getMonth()) {
    return t("window.month_span_single", { month: format(start, "LLLL yyyy", { locale }) });
  }
  // Same year → the year shows once on the end; spanning years → on both sides.
  const startLabel = format(start, sameYear ? "LLLL" : "LLLL yyyy", { locale });
  const endLabel = format(end, "LLLL yyyy", { locale });
  return t("window.month_span_range", { start: startLabel, end: endLabel });
}
