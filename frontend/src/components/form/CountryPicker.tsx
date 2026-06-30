import { useMemo } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCountries } from "@/features/admin/countries/hooks";

// Load the full list in one request — the default page size would truncate the
// ~250-row country list. Capped server-side by ConfigurablePageSizePagination.
const COUNTRY_PAGE_SIZE = 500;

interface CountryPickerProps {
  id?: string;
  value: number | null | undefined;
  onChange: (value: number) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function CountryPicker({ id, value, onChange, placeholder, disabled }: CountryPickerProps) {
  const countriesQuery = useCountries({ pageSize: COUNTRY_PAGE_SIZE, ordering: "name" });

  const options = useMemo(() => {
    const rows = countriesQuery.data?.results ?? [];
    const active = rows.filter((c) => c.is_active);
    // Keep the currently-selected country visible even if it has been
    // deactivated, so editing an existing location never blanks the picker.
    if (value != null && !active.some((c) => c.id === value)) {
      const current = rows.find((c) => c.id === value);
      if (current) return [current, ...active];
    }
    return active;
  }, [countriesQuery.data, value]);

  return (
    <Select
      value={value != null ? String(value) : ""}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled || countriesQuery.isLoading}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
