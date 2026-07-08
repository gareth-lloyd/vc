import { useMemo } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCurrencies } from "@/features/admin/currencies/hooks";

// Local sentinel for the optional "unset" item. Radix Select forbids an empty
// string as an item value, so a null/unset choice needs a non-empty token. This
// is intentionally private to the picker (SettingsTab has its own equivalent
// for its inline Selects) so callers never have to know the wire value.
const UNSET_VALUE = "__unset__";

interface CurrencyPickerProps {
  id?: string;
  value: number | null | undefined;
  onChange: (value: number) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Render a leading "unset" item so the FK can be cleared to null. */
  allowUnset?: boolean;
  /** Label for the unset item (e.g. t("common.unset")). */
  unsetLabel?: string;
  /** Called when the unset item is chosen. */
  onUnset?: () => void;
}

export function CurrencyPicker({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  allowUnset,
  unsetLabel,
  onUnset,
}: CurrencyPickerProps) {
  const currenciesQuery = useCurrencies({});

  const activeCurrencies = useMemo(
    () => (currenciesQuery.data?.results ?? []).filter((c) => c.is_active),
    [currenciesQuery.data],
  );

  // When unset is allowed, map null → the sentinel so the unset item shows as
  // selected (not the placeholder). Otherwise keep the existing null → ""
  // → placeholder behaviour the two existing callers rely on.
  const stringValue = value != null ? String(value) : allowUnset ? UNSET_VALUE : "";

  return (
    <Select
      value={stringValue}
      onValueChange={(v) => (v === UNSET_VALUE ? onUnset?.() : onChange(Number(v)))}
      disabled={disabled || currenciesQuery.isLoading}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowUnset && <SelectItem value={UNSET_VALUE}>{unsetLabel}</SelectItem>}
        {activeCurrencies.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            {c.code} — {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
