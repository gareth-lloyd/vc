import { useRef, useState } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { formatDate, formatWeekRangeCompact } from "@/lib/format/date";
import type { StayOption } from "../schemas";

interface Props {
  options: StayOption[];
  // GAP-043 multi-select: every checked week becomes its own quote line.
  checkedIndices: Set<number>;
  onToggle: (index: number) => void;
  // Weeks already staged in the shortlist — marked Added on their cells.
  stagedIndices: Set<number>;
}

// Shared typographic treatment for the tiny cell markers (Requested / Held /
// Added) so they can't drift apart. A cell can stack several — an intentional,
// meaningful pairing (see the tests).
const CELL_MARKER = "text-[0.625rem] font-medium tracking-wide uppercase";

/**
 * Horizontal week strip for a fixed-changeover result whose flexibility window
 * admits more than one changeover-to-changeover block. A scrollable, chronological
 * row of equal cells reads as a mini calendar of weeks — compact enough to stay
 * usable in the builder column at medium widths (it scrolls rather than wrapping
 * into a tall stack).
 *
 * Cells show only the compact date range; the shared "N-night stays" caption
 * carries nights when every block is the same length, else each cell keeps its
 * own nights sub-label. The `is_default` block (nearest the guest's request) is
 * always tagged Requested; held blocks (`is_available === false`) are shown for
 * context but are NOT checkable — a booked week can't be quoted (the cell is
 * disabled and Arrow nav skips it). Visible text is abbreviated, so each cell
 * carries a full-text `aria-label`.
 *
 * Checkbox-group semantics (GAP-043 multi-week): the operator ticks all the
 * weeks to quote, each becoming its own line. Roving tabindex + Arrow key
 * navigation move FOCUS only (the ARIA group pattern for checkboxes); click or
 * Space toggles the focused cell.
 */
export function StayOptionPicker({ options, checkedIndices, onToggle, stagedIndices }: Props) {
  const { t } = useTranslation("quotations");
  const tr = (key: string, opts?: Record<string, unknown>) =>
    t(`builder.results.stay_options.${key}`, opts);
  const cellRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // The roving tab stop, independent of the checked set: start on the first
  // checked available cell (else the first available), move with the arrows.
  const firstFocusable = () => {
    const checkedAvailable = options.findIndex((o, i) => checkedIndices.has(i) && o.is_available);
    if (checkedAvailable !== -1) return checkedAvailable;
    return Math.max(
      0,
      options.findIndex((o) => o.is_available),
    );
  };
  const [focusIndex, setFocusIndex] = useState(firstFocusable);

  const uniformNights = options.length > 0 && options.every((o) => o.nights === options[0].nights);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    // Step over held (non-checkable) cells, wrapping around; bail if the ring
    // holds no other bookable block.
    let next = focusIndex;
    do {
      next = (next + delta + options.length) % options.length;
    } while (next !== focusIndex && !options[next].is_available);
    if (next === focusIndex || !options[next].is_available) return;
    setFocusIndex(next);
    cellRefs.current[next]?.focus();
  };

  return (
    <div className="space-y-1 pt-2">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-xs font-medium">{tr("label")}</span>
        {uniformNights ? (
          <span className="text-muted-foreground text-xs">
            {tr("caption_nights", { nights: options[0].nights })}
          </span>
        ) : null}
      </div>
      <div
        role="group"
        aria-label={tr("label")}
        onKeyDown={handleKeyDown}
        className="flex gap-2 overflow-x-auto pb-1"
      >
        {options.map((option, index) => {
          const checked = checkedIndices.has(index);
          const ariaLabel = tr("option_aria", {
            range: `${formatDate(option.date_from)} → ${formatDate(option.date_to)}`,
            nights: tr("nights", { count: option.nights }),
            status: option.is_available ? tr("available") : tr("held"),
          });
          return (
            <button
              key={option.date_from}
              ref={(el) => {
                cellRefs.current[index] = el;
              }}
              type="button"
              role="checkbox"
              aria-checked={checked}
              aria-label={ariaLabel}
              disabled={!option.is_available}
              tabIndex={index === focusIndex ? 0 : -1}
              onClick={() => {
                setFocusIndex(index);
                onToggle(index);
              }}
              className={cn(
                "flex min-w-[84px] shrink-0 grow flex-col items-center gap-0.5 rounded-md border px-3 py-2 text-xs transition-colors",
                checked
                  ? "border-primary bg-primary text-primary-foreground"
                  : option.is_available
                    ? "border-border text-muted-foreground hover:text-foreground"
                    : "border-border text-muted-foreground/50 cursor-not-allowed",
              )}
            >
              <span className="flex items-center gap-1 font-medium whitespace-nowrap">
                {checked ? <Check className="size-3 shrink-0" aria-hidden /> : null}
                {formatWeekRangeCompact(option.date_from, option.date_to)}
              </span>
              {!uniformNights ? (
                <span className="text-[0.625rem] opacity-80">
                  {tr("nights", { count: option.nights })}
                </span>
              ) : null}
              {option.is_default ? (
                <span
                  className={cn(
                    CELL_MARKER,
                    checked ? "text-primary-foreground/80" : "text-primary",
                  )}
                >
                  {tr("requested")}
                </span>
              ) : null}
              {!option.is_available ? <span className={CELL_MARKER}>{tr("held")}</span> : null}
              {stagedIndices.has(index) ? (
                <span
                  className={cn(
                    CELL_MARKER,
                    checked ? "text-primary-foreground/80" : "text-success",
                  )}
                >
                  {tr("staged")}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
