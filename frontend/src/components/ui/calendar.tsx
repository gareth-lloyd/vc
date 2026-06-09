import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { el, enGB } from "date-fns/locale";
import "react-day-picker/style.css";
import i18n, { DEFAULT_LANGUAGE } from "@/i18n";
import { baseLanguageTag } from "@/i18n/normalize";
import { cn } from "@/lib/cn";

// react-day-picker ships its own layout/interaction CSS; we only re-skin it to
// the brand by overriding its documented CSS variables (selected / range /
// today colours map onto our shadcn tokens). Keeps this wrapper tiny instead of
// re-implementing the whole grid in Tailwind.
const RDP_THEME = cn(
  "[--rdp-accent-color:var(--primary)]",
  "[--rdp-accent-background-color:var(--accent)]",
  "[--rdp-range_start-color:var(--primary-foreground)]",
  "[--rdp-range_end-color:var(--primary-foreground)]",
  "[--rdp-range_middle-color:var(--accent-foreground)]",
  "[--rdp-today-color:var(--primary)]",
  "[--rdp-day-width:2.5rem]",
  "[--rdp-day_button-width:2.25rem]",
  "[--rdp-day_button-height:2.25rem]",
);

const DATE_FNS_LOCALES = { [DEFAULT_LANGUAGE]: enGB, el } as const;

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

export function Calendar({ className, ...props }: CalendarProps) {
  const locale = DATE_FNS_LOCALES[baseLanguageTag(i18n.language) as "el"] ?? enGB;
  return (
    <DayPicker
      locale={locale}
      weekStartsOn={1}
      className={cn(RDP_THEME, "text-foreground", className)}
      components={{
        Chevron: ({ orientation, className: chevronClassName, ...rest }) => {
          const Icon = orientation === "left" ? ChevronLeft : ChevronRight;
          return <Icon className={cn("size-4", chevronClassName)} {...rest} />;
        },
      }}
      {...props}
    />
  );
}
