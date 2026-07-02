import {
  addDays,
  differenceInCalendarDays,
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
 * Suggest a rate-period end date (inclusive `date_to`) for a property with a
 * fixed weekly changeover day: the day *before* the next changeover that lands
 * at least `minNights` nights after `dateFromIso`. The result is always strictly
 * after `dateFromIso`, so it satisfies the period's `date_to >= date_from`
 * constraint (and here, strictly `>`).
 *
 * Originally shipped as `suggestRateBandEnd` (GAP-025); GAP-056 moved date
 * ownership from the band onto the period, so it now seeds a period's end.
 *
 * Returns `null` when there is no fixed changeover (`"any"`, null, or an unknown
 * code) or `dateFromIso` is empty/unparseable — the caller should leave the
 * field untouched in that case.
 */
export function suggestRatePeriodEnd(
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
 * Shared endpoint collapse: render two dates the way a human says them,
 * dropping the leading date's month/year when the trailing one repeats it,
 * and the dash entirely when they coincide. `keepYear: true` always shows the
 * trailing year and spaces the dash across month boundaries ("29 Jul – 1 Aug
 * 2026"); `keepYear: false` is the compact form — tight dash, year(s) only
 * when the range crosses a year boundary ("25 Jul–1 Aug").
 */
function collapseEndpoints(from: Date, to: Date, { keepYear }: { keepYear: boolean }): string {
  const locale = activeLocale();
  const sameYear = from.getFullYear() === to.getFullYear();
  const sameMonth = sameYear && from.getMonth() === to.getMonth();
  const endFormat = keepYear || !sameYear ? "d MMM yyyy" : "d MMM";
  if (from.getTime() === to.getTime()) {
    return format(to, endFormat, { locale });
  }
  if (sameMonth) {
    return `${format(from, "d", { locale })}–${format(to, endFormat, { locale })}`;
  }
  const startFormat = sameYear ? "d MMM" : "d MMM yyyy";
  const dash = keepYear ? " – " : "–";
  return `${format(from, startFormat, { locale })}${dash}${format(to, endFormat, { locale })}`;
}

/**
 * Render an inclusive night range "21–30 Jul 2026" from its first and last
 * nights (see `nightRangeParts`).
 */
export function formatNightRange(firstNight: Date, lastNight: Date): string {
  return collapseEndpoints(firstNight, lastNight, { keepYear: true });
}

/**
 * Compact changeover-block label from the two ISO endpoints, formatted
 * **directly** (checkout semantics — a block that runs `1 Aug → 8 Aug` reads
 * "1–8 Aug", matching the pill it replaces; do NOT route through
 * `nightRangeParts`, whose `lastNight` is `date_to − 1` and would shift the
 * visible end date). Drops the year within a single year so the week strip's
 * cells stay narrow. Returns "—" when either endpoint is empty or unparseable.
 */
export function formatWeekRangeCompact(dateFrom: string, dateTo: string): string {
  const from = parseISO(dateFrom);
  const to = parseISO(dateTo);
  if (!isValid(from) || !isValid(to)) return "—";
  return collapseEndpoints(from, to, { keepYear: false });
}

/**
 * DateRangePicker trigger label: the two stored ISO endpoints formatted
 * **directly** (in nights mode `dateTo` is the exclusive checkout, shown
 * as-is), year always kept. A valid start with a missing/unparseable end
 * renders open ("12 Jul 2026 – …"); a valid end with a missing/unparseable
 * start renders open the other way ("… – 12 Jul 2026", e.g. a To-only audit
 * filter bound — so the active bound stays visible at the trigger rather than
 * collapsing to the placeholder); only when NEITHER endpoint is set does it
 * return "" so the caller can show its placeholder. An inverted range (mid-edit
 * via the typed inputs) renders both endpoints uncollapsed rather than a
 * garbled "30–1 Jun 2026".
 */
export function formatDateRangeEndpoints(dateFrom: string, dateTo: string): string {
  const from = parseISO(dateFrom);
  const to = parseISO(dateTo);
  const hasFrom = !!dateFrom && isValid(from);
  const hasTo = !!dateTo && isValid(to);
  if (!hasFrom) {
    return hasTo ? `… – ${formatDate(to)}` : "";
  }
  if (!hasTo) {
    return `${formatDate(from)} – …`;
  }
  if (dateTo < dateFrom) {
    return `${formatDate(from)} – ${formatDate(to)}`;
  }
  return collapseEndpoints(from, to, { keepYear: true });
}

/**
 * i18n interpolation args for a "N nights (21–30 Jul 2026)" summary of a
 * half-open `[date_from, date_to)` range, or `null` when it isn't a valid forward
 * span. Callers interpolate these into the shared `common:date_range.nights_summary`
 * key (the block dialogs and DateRangePicker all render the same summary shape).
 */
export function nightsSummaryArgs(
  dateFrom: string,
  dateTo: string,
): { range: string; count: number } | null {
  if (!dateFrom || !dateTo || dateTo <= dateFrom) return null;
  if (!isValid(parseISO(dateFrom)) || !isValid(parseISO(dateTo))) return null;
  const parts = nightRangeParts(dateFrom, dateTo);
  return { range: formatNightRange(parts.firstNight, parts.lastNight), count: parts.nights };
}

/**
 * Inclusive twin of `nightsSummaryArgs` for `[date_from, date_to]` ranges
 * (rate periods, validity windows): "30 days (1–30 Jun 2026)". Equal endpoints
 * are a legal one-day range; returns `null` for a missing endpoint or an
 * inverted range.
 */
export function daysSummaryArgs(
  dateFrom: string,
  dateTo: string,
): { range: string; count: number } | null {
  if (!dateFrom || !dateTo || dateTo < dateFrom) return null;
  const from = parseISO(dateFrom);
  const to = parseISO(dateTo);
  if (!isValid(from) || !isValid(to)) return null;
  return {
    range: collapseEndpoints(from, to, { keepYear: true }),
    count: differenceInCalendarDays(to, from) + 1,
  };
}

export function formatRelative(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return formatDistanceToNow(date, { addSuffix: true, locale: activeLocale() });
}
