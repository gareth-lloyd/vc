// Catalog of settings the backend actually consumes. A key only belongs here
// once code reads it (see `django_res/core/refs.py`); adding a key the platform
// ignores would be dead data, so the Add dialog offers only these entries.
//
// `labelKey` / `descriptionKey` are i18n keys under the `admin` namespace
// (`system.catalog.*`); `defaultValue` mirrors the backend fallback so the
// dialog can pre-fill it.
export interface SettingDefinition {
  key: string;
  labelKey: string;
  descriptionKey: string;
  defaultValue: string;
}

export const SETTINGS_CATALOG: readonly SettingDefinition[] = [
  {
    key: "quotation_no_prefix",
    labelKey: "system.catalog.quotation_no_prefix.label",
    descriptionKey: "system.catalog.quotation_no_prefix.description",
    defaultValue: "QVC",
  },
  {
    key: "booking_no_prefix",
    labelKey: "system.catalog.booking_no_prefix.label",
    descriptionKey: "system.catalog.booking_no_prefix.description",
    defaultValue: "VC",
  },
] as const;

const CATALOG_BY_KEY = new Map(SETTINGS_CATALOG.map((d) => [d.key, d]));

export function getSettingDefinition(key: string): SettingDefinition | undefined {
  return CATALOG_BY_KEY.get(key);
}
