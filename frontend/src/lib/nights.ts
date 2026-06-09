import { differenceInCalendarDays, parseISO, subDays } from "date-fns";

/**
 * Helpers for turning a half-open booking range `[date_from, date_to)` — where
 * `date_to` is the exclusive checkout morning — into the inclusive nights a human
 * actually thinks about. Mirrors the backend `nights()` in
 * `django_res/pricing/services/rates.py`.
 *
 * These return structured parts (Dates / counts), never pre-translated strings:
 * the calling component owns formatting and i18n (singular vs plural, locale).
 */

/** The last night actually slept: exclusive `date_to` minus one day. */
export function lastNight(dateTo: string): Date {
  return subDays(parseISO(dateTo), 1);
}

/** Number of nights in the half-open range `[date_from, date_to)`. */
export function nightsCount(dateFrom: string, dateTo: string): number {
  return Math.max(0, differenceInCalendarDays(parseISO(dateTo), parseISO(dateFrom)));
}

export interface NightRangeParts {
  firstNight: Date;
  lastNight: Date;
  nights: number;
}

/**
 * Decompose a half-open range into the first night, last night and night count.
 * For a single-night range (`21 → 22`) `firstNight` and `lastNight` coincide so
 * the caller renders "21 Jul · 1 night", never "21–21 Jul".
 */
export function nightRangeParts(dateFrom: string, dateTo: string): NightRangeParts {
  return {
    firstNight: parseISO(dateFrom),
    lastNight: lastNight(dateTo),
    nights: nightsCount(dateFrom, dateTo),
  };
}
