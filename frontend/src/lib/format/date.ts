import { format, formatDistanceToNow, isValid, parseISO, type Locale } from "date-fns";
import { enGB } from "date-fns/locale";
import i18n, { DEFAULT_LANGUAGE } from "@/i18n";
import { baseLanguageTag } from "@/i18n/normalize";

// Register additional date-fns locales here when adding a new translated language.
const LOCALES: Record<string, Locale> = {
  [DEFAULT_LANGUAGE]: enGB,
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

export function formatRelative(value: string | Date | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(date)) return "—";
  return formatDistanceToNow(date, { addSuffix: true, locale: activeLocale() });
}
