import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import type { StayOption } from "../schemas";

interface Props {
  options: StayOption[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

/**
 * Radio-chip row for a fixed-changeover result whose flexibility window
 * admits more than one changeover-to-changeover block. Held blocks stay
 * selectable (the operator may want to see their price); the Add button is
 * what the parent disables.
 */
export function StayOptionPicker({ options, selectedIndex, onSelect }: Props) {
  const { t } = useTranslation("quotations");

  return (
    <div
      role="radiogroup"
      aria-label={t("builder.results.stay_options.label")}
      className="flex flex-wrap gap-1.5"
    >
      {options.map((option, index) => {
        const selected = index === selectedIndex;
        return (
          <button
            key={option.date_from}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onSelect(index)}
            className={cn(
              "rounded-md border px-2 py-1 text-xs transition-colors",
              selected
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {formatDate(option.date_from)} → {formatDate(option.date_to)}
            {" · "}
            {t("builder.results.stay_options.nights", { count: option.nights })}
            {" · "}
            <span className={option.is_available ? undefined : "font-medium"}>
              {option.is_available
                ? t("builder.results.stay_options.available")
                : t("builder.results.stay_options.held")}
            </span>
          </button>
        );
      })}
    </div>
  );
}
