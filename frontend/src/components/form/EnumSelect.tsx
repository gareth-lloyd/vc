import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface EnumSelectProps<T extends string> {
  id?: string;
  /** The current enum value ("" shows the placeholder). */
  value: string;
  onChange: (value: T) => void;
  options: readonly T[];
  /** Maps an enum value to its translated label. */
  labelFor: (value: T) => string;
  placeholder?: string;
}

/**
 * A thin `Select` over a fixed enum (mirrors the backend choices) — a leaf
 * input like `CountryPicker`, not a form abstraction. Radix rejects
 * `value=""`, so an empty value falls back to `undefined` (which surfaces the
 * placeholder).
 */
export function EnumSelect<T extends string>({
  id,
  value,
  onChange,
  options,
  labelFor,
  placeholder,
}: EnumSelectProps<T>) {
  return (
    // Radix only ever emits a value that was rendered as an option, so the
    // cast back to T is sound.
    <Select value={value || undefined} onValueChange={(v) => onChange(v as T)}>
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
