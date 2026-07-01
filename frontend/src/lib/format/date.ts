import { addDays, format, formatDistanceToNow, isValid, parseISO, type Locale } from "date-fns";
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
 * Compact changeover-block label from the two ISO endpoints, formatted
 * **directly** (checkout semantics — a block that runs `1 Aug → 8 Aug` reads
 * "1–8 Aug", matching the pill it replaces; do NOT route through
 * `nightRangeParts`, whose `lastNight` is `date_to − 1` and would shift the
 * visible end date). Drops the year within a single year and the shared month
 * when both endpoints land in it, so the week strip's cells stay narrow:
 * `1–8 Aug`, `25 Jul–1 Aug`, `27 Dec 2026–3 Jan 2027`. Returns "—" when either
 * endpoint is empty or unparseable.
 */
export function formatWeekRangeCompact(dateFrom: string, dateTo: string): string {
  const from = parseISO(dateFrom);
  const to = parseISO(dateTo);
  if (!isValid(from) || !isValid(to)) return "—";
  const locale = activeLocale();
  const sameYear = from.getFullYear() === to.getFullYear();
  const sameMonth = sameYear && from.getMonth() === to.getMonth();
  if (sameMonth) {
    return `${format(from, "d", { locale })}–${format(to, "d MMM", { locale })}`;
  }
  const endpointFormat = sameYear ? "d MMM" : "d MMM yyyy";
  return `${format(from, endpointFormat, { locale })}–${format(to, endpointFormat, { locale })}`;
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
