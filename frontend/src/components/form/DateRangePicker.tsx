import { useState } from "react";
import { useController, type Control, type FieldPath, type FieldValues } from "react-hook-form";
import { addDays, format, isValid, parseISO } from "date-fns";
import { CalendarDays } from "lucide-react";
import type { DateRange, Matcher } from "react-day-picker";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { daysSummaryArgs, formatDateRangeEndpoints, nightsSummaryArgs } from "@/lib/format/date";
import { lastNight } from "@/lib/nights";
import { useMediaQuery } from "@/lib/useMediaQuery";

const ISO = "yyyy-MM-dd";

function toDate(value: string): Date | undefined {
  if (!value) return undefined;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : undefined;
}

/**
 * - `nights`: half-open `[date_from, date_to)` — the stored `date_to` is the
 *   exclusive checkout morning. The calendar speaks **inclusive nights** (pick
 *   first and last night) and the picker writes `date_to = last night + 1`.
 * - `days`: inclusive `[date_from, date_to]` — endpoints stored verbatim, a
 *   single-day range is legal.
 */
export type DateRangePickerMode = "nights" | "days";

interface DateRangePickerProps<T extends FieldValues> {
  control: Control<T>;
  fromName: FieldPath<T>;
  toName: FieldPath<T>;
  mode: DateRangePickerMode;
  /** Visible label above the trigger. */
  label: string;
  /** Trigger id; the popover input / error / summary ids derive from it. */
  id: string;
  /** Labels for the typed ISO inputs inside the popover. */
  fromLabel: string;
  toLabel: string;
  /** Trigger text when no start date is set; defaults to the common placeholder. */
  placeholder?: string;
  disabled?: boolean;
  /** Days the calendar greys out (occupied dates etc.). */
  disabledDays?: Matcher | Matcher[];
  /** ISO bounds mapped onto DayPicker `before`/`after` matchers. */
  minDate?: string;
  maxDate?: string;
  /** Reset a selection that would span a disabled day to the clicked day.
   * Defaults on in nights mode when `disabledDays` is set. */
  excludeDisabled?: boolean;
  /** Fires when the calendar popover opens/closes. Lets the host defer the
   * (only popover-consumed) availability fetch until the picker is opened. */
  onPickerOpenChange?: (open: boolean) => void;
  /** Pre-resolved (translated) field errors — rendered OUTSIDE the popover so
   * a failed submit shows them with the picker closed. */
  fromError?: string;
  toError?: string;
  /** Defaults responsive: 2 months at ≥640px, 1 below. */
  numberOfMonths?: 1 | 2;
  defaultMonth?: Date;
}

/**
 * Standard date-range input: a single labelled trigger showing the formatted
 * range ("12–19 Jul 2026 · 7 nights") that opens a range calendar with typed
 * ISO fallback inputs, a live summary, and Clear/Done. RHF is the single
 * source of truth — selections commit to the two flat fields live; zod schemas
 * own validation and this component only displays the resolved errors.
 * Re-click semantics are react-day-picker's default `addToRange` (click after
 * the end extends, inside shrinks, endpoint collapses) — pinned by test;
 * `resetOnSelect` stays off.
 */
export function DateRangePicker<T extends FieldValues>({
  control,
  fromName,
  toName,
  mode,
  label,
  id,
  fromLabel,
  toLabel,
  placeholder,
  disabled,
  disabledDays,
  minDate,
  maxDate,
  excludeDisabled,
  onPickerOpenChange,
  fromError,
  toError,
  numberOfMonths,
  defaultMonth,
}: DateRangePickerProps<T>) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const from = useController({ control, name: fromName });
  const to = useController({ control, name: toName });

  const fromValue = (from.field.value as string) || "";
  const toValue = (to.field.value as string) || "";
  const fromDate = toDate(fromValue);
  const toDateValue = toDate(toValue);

  const isWide = useMediaQuery("(min-width: 640px)");
  const months = numberOfMonths ?? (isWide ? 2 : 1);

  // Highlight inclusive nights, so the stored exclusive checkout (date_to) is
  // shown as the last night slept; days mode highlights endpoints verbatim.
  const selected: DateRange | undefined = fromDate
    ? {
        from: fromDate,
        to: toDateValue ? (mode === "nights" ? lastNight(toValue) : toDateValue) : undefined,
      }
    : undefined;

  const handleSelect = (range: DateRange | undefined) => {
    if (!range?.from) {
      from.field.onChange("");
      to.field.onChange("");
      return;
    }
    from.field.onChange(format(range.from, ISO));
    const end = range.to ?? range.from;
    to.field.onChange(format(mode === "nights" ? addDays(end, 1) : end, ISO));
  };

  const summary =
    mode === "nights" ? nightsSummaryArgs(fromValue, toValue) : daysSummaryArgs(fromValue, toValue);
  const rangeText = formatDateRangeEndpoints(fromValue, toValue);
  // Empty OR unparseable start → placeholder; partial/inverted → raw endpoints.
  const showPlaceholder = !rangeText;
  const triggerText = summary
    ? t(mode === "nights" ? "date_range.trigger_nights" : "date_range.trigger_days", {
        range: rangeText,
        count: summary.count,
      })
    : rangeText || (placeholder ?? t("date_range.placeholder"));

  const matchers: Matcher[] = disabledDays
    ? Array.isArray(disabledDays)
      ? [...disabledDays]
      : [disabledDays]
    : [];
  if (minDate) matchers.push({ before: parseISO(minDate) });
  if (maxDate) matchers.push({ after: parseISO(maxDate) });

  const describedBy =
    [fromError && `${id}-from-error`, toError && `${id}-to-error`].filter(Boolean).join(" ") ||
    undefined;

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    onPickerOpenChange?.(next);
    if (!next) {
      // Touched bookkeeping only — the host forms validate on submit.
      from.field.onBlur();
      to.field.onBlur();
    }
  };

  return (
    <div className="space-y-2">
      <Label id={`${id}-label`} htmlFor={id}>
        {label}
      </Label>
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            id={id}
            variant="outline"
            disabled={disabled}
            className="w-full justify-start font-normal"
            aria-invalid={!!(fromError || toError)}
            aria-describedby={describedBy}
            // A <button> is labelable, so the <Label> alone would REPLACE the
            // accessible name and hide the selected range from AT — name it
            // with label + current value instead.
            aria-labelledby={`${id}-label ${id}-value`}
          >
            <CalendarDays className="mr-2 size-4" />
            <span
              id={`${id}-value`}
              className={showPlaceholder ? "text-muted-foreground" : undefined}
            >
              {triggerText}
            </span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="range"
            selected={selected}
            onSelect={handleSelect}
            disabled={matchers.length ? matchers : undefined}
            excludeDisabled={excludeDisabled ?? (mode === "nights" && disabledDays != null)}
            numberOfMonths={months}
            defaultMonth={fromDate ?? defaultMonth}
            autoFocus
          />
          <div className="space-y-3 border-t p-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor={`${id}-from`}>{fromLabel}</Label>
                <Input
                  id={`${id}-from`}
                  type="date"
                  value={fromValue}
                  onChange={(event) => from.field.onChange(event.target.value)}
                  onBlur={from.field.onBlur}
                  aria-invalid={!!fromError}
                  aria-describedby={fromError ? `${id}-from-error` : undefined}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`${id}-to`}>{toLabel}</Label>
                <Input
                  id={`${id}-to`}
                  type="date"
                  value={toValue}
                  onChange={(event) => to.field.onChange(event.target.value)}
                  onBlur={to.field.onBlur}
                  aria-invalid={!!toError}
                  aria-describedby={toError ? `${id}-to-error` : undefined}
                />
              </div>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span data-testid={`${id}-summary`} className="text-muted-foreground text-sm">
                {summary
                  ? t(mode === "nights" ? "date_range.nights_summary" : "date_range.days_summary", {
                      count: summary.count,
                      range: summary.range,
                    })
                  : null}
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    from.field.onChange("");
                    to.field.onChange("");
                  }}
                >
                  {t("actions.clear")}
                </Button>
                <Button type="button" size="sm" onClick={() => handleOpenChange(false)}>
                  {t("date_range.done")}
                </Button>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
      {fromError ? (
        <p id={`${id}-from-error`} className="text-destructive text-sm" role="alert">
          {fromError}
        </p>
      ) : null}
      {toError ? (
        <p id={`${id}-to-error`} className="text-destructive text-sm" role="alert">
          {toError}
        </p>
      ) : null}
    </div>
  );
}
