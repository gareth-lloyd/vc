import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";

/**
 * Horizontal status tab-bar with live count badges that doubles as the status
 * filter (mock-up 01). Selecting a chip sets the active status; the leading
 * "all" chip clears it. Counts come from a `:status-counts` aggregate so the
 * bar never fans out one request per status.
 */
export interface StatusFilterOption {
  value: string;
  label: string;
}

interface StatusFilterBarProps {
  options: StatusFilterOption[];
  counts: Record<string, number> | undefined;
  value: string | undefined;
  onChange: (value: string | undefined) => void;
  allLabel: string;
  className?: string;
}

function Chip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number | undefined;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded-pill flex items-center gap-1.5 border px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30",
      )}
    >
      <span>{label}</span>
      {count != null ? (
        <span
          className={cn(
            "text-xs tabular-nums",
            active ? "text-primary-foreground/80" : "text-muted-foreground/70",
          )}
        >
          {count}
        </span>
      ) : null}
    </button>
  );
}

export function StatusFilterBar({
  options,
  counts,
  value,
  onChange,
  allLabel,
  className,
}: StatusFilterBarProps) {
  const { t } = useTranslation("common");
  const total = counts ? Object.values(counts).reduce((sum, n) => sum + n, 0) : undefined;
  return (
    <div
      role="tablist"
      aria-label={t("status_filter.aria_label")}
      className={cn("flex flex-wrap items-center gap-2", className)}
    >
      <Chip
        label={allLabel}
        count={total}
        active={value == null}
        onClick={() => onChange(undefined)}
      />
      {options.map((option) => (
        <Chip
          key={option.value}
          label={option.label}
          count={counts?.[option.value] ?? 0}
          active={value === option.value}
          onClick={() => onChange(option.value)}
        />
      ))}
    </div>
  );
}
