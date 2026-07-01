import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface EnumSelectProps {
  id?: string;
  /** The current enum value ("" shows the placeholder). */
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
  /** Maps an enum value to its translated label. */
  labelFor: (value: string) => string;
  placeholder?: string;
}

/**
 * A thin `Select` over a fixed enum (mirrors the backend choices). Shared by the
 * Extra/Discount form dialogs — a leaf input like `CurrencyPicker`, not a form
 * abstraction. Radix rejects `value=""`, so an empty value falls back to
 * `undefined` (which surfaces the placeholder).
 */
export function EnumSelect({
  id,
  value,
  onChange,
  options,
  labelFor,
  placeholder,
}: EnumSelectProps) {
  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {labelFor(o)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
