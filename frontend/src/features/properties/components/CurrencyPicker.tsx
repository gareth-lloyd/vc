import { useMemo } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCurrencies } from "@/features/admin/currencies/hooks";

interface CurrencyPickerProps {
  id?: string;
  value: number | null | undefined;
  onChange: (value: number) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function CurrencyPicker({
  id,
  value,
  onChange,
  placeholder,
  disabled,
}: CurrencyPickerProps) {
  const currenciesQuery = useCurrencies({});

  const activeCurrencies = useMemo(
    () => (currenciesQuery.data?.results ?? []).filter((c) => c.is_active),
    [currenciesQuery.data],
  );

  const stringValue = value != null ? String(value) : "";

  return (
    <Select
      value={stringValue}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled || currenciesQuery.isLoading}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {activeCurrencies.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            {c.code} — {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
