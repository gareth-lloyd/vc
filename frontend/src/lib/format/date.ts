import { format, formatDistanceToNow, isValid, parseISO, type Locale } from "date-fns";
import { el, enGB } from "date-fns/locale";
import i18n, { DEFAULT_LANGUAGE } from "@/i18n";
import { baseLanguageTag } from "@/i18n/normalize";

// Register additional date-fns locales here when adding a new translated language.
const LOCALES: Record<string, Locale> = {
  [DEFAULT_LANGUAGE]: enGB,
  el,
};

function activeLocale(): Locale {
  return LOCALES[baseLanguageTag(i18n.language)] ?? enGB;
}

export function formatDate(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return format(date, "d MMM yyyy", { locale: activeLocale() });
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

export function formatRelative(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return formatDistanceToNow(date, { addSuffix: true, locale: activeLocale() });
}
