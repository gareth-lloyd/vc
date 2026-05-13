import { DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES } from "./index";

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Strip region subtag and lowercase (`"en-GB"` → `"en"`). */
export function baseLanguageTag(value: string | null | undefined): string {
  return (value?.toLowerCase() ?? DEFAULT_LANGUAGE).split("-")[0];
}

/** Same as `baseLanguageTag` but falls back to `DEFAULT_LANGUAGE` for unsupported tags. */
export function toSupportedLanguage(value: string | null | undefined): SupportedLanguage {
  const base = baseLanguageTag(value);
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(base)
    ? (base as SupportedLanguage)
    : DEFAULT_LANGUAGE;
}
