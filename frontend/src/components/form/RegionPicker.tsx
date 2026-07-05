import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRegions } from "@/lib/geo/hooks";
import type { Region } from "@/lib/geo/schemas";

// Radix SelectItem forbids an empty-string value, so the clearable "All
// regions" row maps to/from this sentinel.
const ALL_VALUE = "__all__";

interface RegionPickerProps {
  id?: string;
  value: number | null | undefined;
  // Receives null only when `clearable` and the "All regions" row is picked.
  onChange: (value: number | null) => void;
  // Offer an "All regions" row that clears the selection (filter-style
  // callers); without it a null value renders the placeholder.
  clearable?: boolean;
  // Scope the options to one country — pass whichever the caller holds.
  // Narrowing is client-side (the full list is fetched once, like
  // CountryPicker) so an out-of-scope current value can stay visible.
  countryId?: number | null;
  countryIso2?: string | null;
  // Only regions that actually hold properties (server-side narrowing).
  hasProperties?: boolean;
  placeholder?: string;
  disabled?: boolean;
}

export function RegionPicker({
  id,
  value,
  onChange,
  clearable,
  countryId,
  countryIso2,
  hasProperties,
  placeholder,
  disabled,
}: RegionPickerProps) {
  const { t } = useTranslation("common");
  const regionsQuery = useRegions(hasProperties ? { hasProperties } : undefined);
  const scoped = countryId != null || !!countryIso2;

  const options = useMemo(() => {
    const rows = regionsQuery.data?.results ?? [];
    // Old bookmarks/params may carry lowercase codes — compare case-blind.
    const iso = countryIso2 ? countryIso2.toUpperCase() : null;
    const inScope = (r: Region) =>
      (countryId == null || r.country === countryId) &&
      (iso == null || (r.country_iso2 ?? "").toUpperCase() === iso);
    const active = rows.filter((r) => r.is_active && inScope(r));
    // Keep the currently-selected region visible even if deactivated or out
    // of the country scope, so editing an existing record never blanks the
    // picker (mirrors CountryPicker).
    if (value != null && !active.some((r) => r.id === value)) {
      const current = rows.find((r) => r.id === value);
      if (current) return [current, ...active];
    }
    return active;
  }, [regionsQuery.data, value, countryId, countryIso2]);

  // Region names repeat across countries; when the picker isn't scoped to
  // one country the ISO suffix disambiguates.
  const label = (r: Region) =>
    !scoped && r.country_iso2 ? `${r.name} (${r.country_iso2})` : r.name;

  return (
    <Select
      value={value != null ? String(value) : clearable ? ALL_VALUE : ""}
      onValueChange={(v) => onChange(v === ALL_VALUE ? null : Number(v))}
      disabled={disabled || regionsQuery.isLoading}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {clearable ? <SelectItem value={ALL_VALUE}>{t("filters.any_region")}</SelectItem> : null}
        {options.map((r) => (
          <SelectItem key={r.id} value={String(r.id)}>
            {label(r)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
