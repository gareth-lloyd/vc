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
