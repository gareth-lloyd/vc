import { useState } from "react";
import { useController, type Control, type FieldPath, type FieldValues } from "react-hook-form";
import { addDays, format, isValid, parseISO } from "date-fns";
import { CalendarDays } from "lucide-react";
import type { DateRange, Matcher } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { lastNight } from "@/lib/nights";

const ISO = "yyyy-MM-dd";

function toDate(value: string): Date | undefined {
  if (!value) return undefined;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : undefined;
}

interface DateRangeFieldProps<T extends FieldValues> {
  control: Control<T>;
  fromName: FieldPath<T>;
  toName: FieldPath<T>;
  fromLabel: string;
  toLabel: string;
  fromId: string;
  toId: string;
  /** Label for the popover trigger ("Pick on calendar"). */
  pickLabel: string;
  /** Days the calendar greys out (already-occupied dates). */
  disabledDays?: Matcher | Matcher[];
  /** Fires when the calendar popover opens/closes. Lets the host defer the
   * (only popover-consumed) availability fetch until the picker is first opened. */
  onPickerOpenChange?: (open: boolean) => void;
  /** Pre-resolved (translated) field errors. */
  fromError?: string;
  toError?: string;
}

/**
 * @deprecated Legacy block-range picker — use {@link DateRangePicker}
 * (`@/components/form/DateRangePicker`, `mode="nights"`) for new work; it is
 * the standard single-trigger control this component predates. Kept only for
 * the owner-portal `BlockRequestDialog`; delete once that host migrates.
 *
 * Typed `<input type="date">` fields for power users plus a visual range
 * calendar. The calendar speaks **inclusive nights** — the user picks the
 * first and last night they want blocked — while the form stores the
 * canonical half-open range (`date_to` = last night + 1 = checkout morning).
 * Typed entry stays bound to the raw stored values; the live nights summary
 * the dialogs render disambiguates either path.
 */
export function DateRangeField<T extends FieldValues>({
  control,
  fromName,
  toName,
  fromLabel,
  toLabel,
  fromId,
  toId,
  pickLabel,
  disabledDays,
  onPickerOpenChange,
  fromError,
  toError,
}: DateRangeFieldProps<T>) {
  const [open, setOpen] = useState(false);
  const from = useController({ control, name: fromName });
  const to = useController({ control, name: toName });

  const fromValue = (from.field.value as string) || "";
  const toValue = (to.field.value as string) || "";
  const fromDate = toDate(fromValue);

  // Highlight the inclusive nights, so the stored exclusive checkout (date_to)
  // is shown as the last night slept, not the morning after.
  const selected: DateRange | undefined = fromDate
    ? { from: fromDate, to: toValue ? lastNight(toValue) : undefined }
    : undefined;

  const handleSelect = (range: DateRange | undefined) => {
    if (!range?.from) {
      from.field.onChange("");
      to.field.onChange("");
      return;
    }
    from.field.onChange(format(range.from, ISO));
    // Half-open store: checkout is the morning after the last selected night.
    const lastSelectedNight = range.to ?? range.from;
    to.field.onChange(format(addDays(lastSelectedNight, 1), ISO));
  };

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor={fromId}>{fromLabel}</Label>
          <Input
            id={fromId}
            type="date"
            value={fromValue}
            onChange={(event) => from.field.onChange(event.target.value)}
            onBlur={from.field.onBlur}
            aria-invalid={!!fromError}
          />
          {fromError ? (
            <p className="text-destructive text-sm" role="alert">
              {fromError}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor={toId}>{toLabel}</Label>
          <Input
            id={toId}
            type="date"
            value={toValue}
            onChange={(event) => to.field.onChange(event.target.value)}
            onBlur={to.field.onBlur}
            aria-invalid={!!toError}
          />
          {toError ? (
            <p className="text-destructive text-sm" role="alert">
              {toError}
            </p>
          ) : null}
        </div>
      </div>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          onPickerOpenChange?.(next);
        }}
      >
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="w-full justify-start">
            <CalendarDays className="mr-2 size-4" />
            {pickLabel}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="range"
            selected={selected}
            onSelect={handleSelect}
            disabled={disabledDays}
            defaultMonth={fromDate}
            autoFocus
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
