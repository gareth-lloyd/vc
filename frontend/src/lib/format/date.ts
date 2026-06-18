import {
  addDays,
  format,
  formatDistanceToNow,
  getDay,
  isValid,
  parseISO,
  type Locale,
} from "date-fns";
import { el, enGB } from "date-fns/locale";
import i18n, { DEFAULT_LANGUAGE } from "@/i18n";
import { baseLanguageTag } from "@/i18n/normalize";
import { nightRangeParts } from "@/lib/nights";

// Register additional date-fns locales here when adding a new translated language.
const LOCALES: Record<string, Locale> = {
  [DEFAULT_LANGUAGE]: enGB,
  el,
};

/** The date-fns locale for the active UI language (the single source of truth —
 * `ui/calendar.tsx` reuses this so the picker can't drift from the formatters). */
export function activeLocale(): Locale {
  return LOCALES[baseLanguageTag(i18n.language)] ?? enGB;
}

export function formatDate(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return format(date, "d MMM yyyy", { locale: activeLocale() });
}

/** Shift an ISO `yyyy-MM-dd` date by whole days, returning the same shape. */
export function addDaysIso(isoDate: string, days: number): string {
  return format(addDays(parseISO(isoDate), days), "yyyy-MM-dd");
}

/** Changeover day codes (`PROPERTY_CHANGEOVER_DAYS`) → `date-fns` `getDay` index
 * (0 = Sunday … 6 = Saturday). `"any"` and unknown codes are absent on purpose:
 * no fixed weekday → no suggestion. */
const CHANGEOVER_WEEKDAY_INDEX: Record<string, number> = {
  sun: 0,
  mon: 1,
  tue: 2,
  wed: 3,
  thu: 4,
  fri: 5,
  sat: 6,
};

/**
 * Suggest a rate-band end date (inclusive `date_to`) for a property with a fixed
 * weekly changeover day: the day *before* the next changeover that lands at least
 * `minNights` nights after `dateFromIso`. The result is always strictly after
 * `dateFromIso`, so it satisfies the rule's `date_to > date_from` constraint.
 *
 * Returns `null` when there is no fixed changeover (`"any"`, null, or an unknown
 * code) or `dateFromIso` is empty/unparseable — the caller should leave the field
 * untouched in that case.
 */
export function suggestRateBandEnd(
  dateFromIso: string,
  changeoverDay: string | null | undefined,
  minNights: number | null | undefined,
): string | null {
  if (!dateFromIso) return null;
  const targetIndex = changeoverDay == null ? undefined : CHANGEOVER_WEEKDAY_INDEX[changeoverDay];
  if (targetIndex === undefined) return null;
  const from = parseISO(dateFromIso);
  if (!isValid(from)) return null;
  // Floor at `minNights`, but never below 2 days out — the next changeover must
  // be ≥ 2 days away so `date_to` (changeover − 1) stays strictly after `date_from`.
  const floor = Math.max(minNights && minNights > 0 ? minNights : 1, 2);
  for (let offset = floor; offset < floor + 7; offset += 1) {
    if (getDay(addDays(from, offset)) === targetIndex) {
      return format(addDays(from, offset - 1), "yyyy-MM-dd");
    }
  }
  return null; // unreachable: a weekday always recurs within any 7-day window
}

/**
 * The local `yyyy-MM-dd'T'HH:mm` shape a `datetime-local` input needs, from a
 * Date or an ISO string. Slicing a UTC ISO string instead would render UTC
 * wall-clock and shift the displayed day in any non-UTC zone.
 */
export function toDatetimeLocal(value: string | Date): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return format(date, "yyyy-MM-dd'T'HH:mm");
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return format(date, "d MMM yyyy HH:mm", { locale: activeLocale() });
}

/**
 * Render an inclusive night range "21–30 Jul 2026" from its first and last
 * nights (see `nightRangeParts`). Collapses shared month/year so the label reads
 * the way a human says it, and drops the dash entirely for a single night.
 */
export function formatNightRange(firstNight: Date, lastNight: Date): string {
  const locale = activeLocale();
  if (firstNight.getTime() === lastNight.getTime()) {
    return format(firstNight, "d MMM yyyy", { locale });
  }
  const sameYear = firstNight.getFullYear() === lastNight.getFullYear();
  const sameMonth = sameYear && firstNight.getMonth() === lastNight.getMonth();
  if (sameMonth) {
    return `${format(firstNight, "d", { locale })}–${format(lastNight, "d MMM yyyy", { locale })}`;
  }
  const firstFormat = sameYear ? "d MMM" : "d MMM yyyy";
  return `${format(firstNight, firstFormat, { locale })} – ${format(lastNight, "d MMM yyyy", { locale })}`;
}

/**
 * i18n interpolation args for a "N nights (21–30 Jul 2026)" summary of a
 * half-open `[date_from, date_to)` range, or `null` when it isn't a valid forward
 * span. The caller owns the translation key — the block dialogs live in different
 * namespaces but share this shape.
 */
export function nightsSummaryArgs(
  dateFrom: string,
  dateTo: string,
): { range: string; count: number } | null {
  if (!dateFrom || !dateTo || dateTo <= dateFrom) return null;
  const parts = nightRangeParts(dateFrom, dateTo);
  return { range: formatNightRange(parts.firstNight, parts.lastNight), count: parts.nights };
}

export function formatRelative(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return formatDistanceToNow(date, { addSuffix: true, locale: activeLocale() });
}
