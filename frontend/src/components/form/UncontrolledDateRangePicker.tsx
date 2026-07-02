import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { DateRangePicker, type DateRangePickerMode } from "./DateRangePicker";

interface RangeValue {
  from: string;
  to: string;
}

export interface UncontrolledDateRangePickerProps {
  /** Current range, owned by the host (plain ISO strings, either side blank). */
  value: RangeValue;
  /** Fires on every committed edit (typed input, calendar click, Clear). A
   * single calendar click writes `from` then `to`, so this may fire twice in a
   * batch — emissions are **latest-wins**, the final pair is authoritative. */
  onChange: (from: string, to: string) => void;
  mode: DateRangePickerMode;
  label: string;
  id: string;
  fromLabel: string;
  toLabel: string;
  placeholder?: string;
  disabled?: boolean;
  numberOfMonths?: 1 | 2;
  defaultMonth?: Date;
}

/**
 * Adapter that lets non-RHF hosts (`useState`-driven filter bars, probe panels)
 * use the standard {@link DateRangePicker} without adopting react-hook-form.
 * It owns a private `useForm` synced to `value` via RHF's `values` option (a
 * deep-compare guards the reset, so a fresh `{from,to}` literal per host render
 * does not loop) and re-emits internal edits through `onChange`. Host-driven
 * `value` changes propagate down without echoing back up.
 */
export function UncontrolledDateRangePicker({
  value,
  onChange,
  mode,
  label,
  id,
  fromLabel,
  toLabel,
  placeholder,
  disabled,
  numberOfMonths,
  defaultMonth,
}: UncontrolledDateRangePickerProps) {
  const form = useForm<RangeValue>({
    defaultValues: { from: value.from, to: value.to },
    values: { from: value.from, to: value.to },
  });

  useEffect(() => {
    const subscription = form.watch((next) => {
      const from = next.from ?? "";
      const to = next.to ?? "";
      // Skip the echo when the change is the `values` sync catching up to a
      // host-driven `value` (down-propagation), not a user edit.
      if (from === value.from && to === value.to) return;
      onChange(from, to);
    });
    return () => subscription.unsubscribe();
  }, [form, onChange, value.from, value.to]);

  return (
    <DateRangePicker
      control={form.control}
      fromName="from"
      toName="to"
      mode={mode}
      label={label}
      id={id}
      fromLabel={fromLabel}
      toLabel={toLabel}
      placeholder={placeholder}
      disabled={disabled}
      numberOfMonths={numberOfMonths}
      defaultMonth={defaultMonth}
    />
  );
}
