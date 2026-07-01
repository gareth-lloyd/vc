import { useRef } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { formatDate, formatWeekRangeCompact } from "@/lib/format/date";
import type { StayOption } from "../schemas";

interface Props {
  options: StayOption[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

// Shared typographic treatment for the tiny cell markers (Requested / Held) so
// the two can't drift apart. A cell that is both the requested block AND held
// shows both, stacked — an intentional, meaningful pairing (see the test).
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
 * context but are NOT selectable — a booked week can't be quoted, so it never
 * becomes the active choice (the cell is disabled and Arrow nav skips it). The
 * caller (`QuoteResultLine`) preselects the first bookable block, so a held
 * default hands off to an available alternative. Visible text is abbreviated,
 * so each cell carries a full-text `aria-label`.
 *
 * Radiogroup semantics with a roving tabindex + Arrow key navigation (the ARIA
 * radiogroup pattern): the selected cell is the sole tab stop, and ArrowLeft/Right
 * move selection + focus with wrap-around, skipping held cells. Props are
 * unchanged from the old pill row so `QuoteResultLine` needs no change.
 */
export function StayOptionPicker({ options, selectedIndex, onSelect }: Props) {
  const { t } = useTranslation("quotations");
  const tr = (key: string, opts?: Record<string, unknown>) =>
    t(`builder.results.stay_options.${key}`, opts);
  const cellRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const uniformNights = options.length > 0 && options.every((o) => o.nights === options[0].nights);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    // Step over held (non-selectable) cells, wrapping around; bail if the ring
    // holds no other bookable block.
    let next = selectedIndex;
    do {
      next = (next + delta + options.length) % options.length;
    } while (next !== selectedIndex && !options[next].is_available);
    if (next === selectedIndex || !options[next].is_available) return;
    onSelect(next);
    // Focus the target now — it already exists in the DOM (just tab-inert); the
    // re-render then makes it the tab stop. Keeps focus on the moving selection.
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
        role="radiogroup"
        aria-label={tr("label")}
        onKeyDown={handleKeyDown}
        className="flex gap-2 overflow-x-auto pb-1"
      >
        {options.map((option, index) => {
          const selected = index === selectedIndex;
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
              role="radio"
              aria-checked={selected}
              aria-label={ariaLabel}
              disabled={!option.is_available}
              tabIndex={selected ? 0 : -1}
              onClick={() => onSelect(index)}
              className={cn(
                "flex min-w-[84px] shrink-0 grow flex-col items-center gap-0.5 rounded-md border px-3 py-2 text-xs transition-colors",
                selected
                  ? "border-primary bg-primary text-primary-foreground"
                  : option.is_available
                    ? "border-border text-muted-foreground hover:text-foreground"
                    : "border-border text-muted-foreground/50 cursor-not-allowed",
              )}
            >
              <span className="flex items-center gap-1 font-medium whitespace-nowrap">
                {selected ? <Check className="size-3 shrink-0" aria-hidden /> : null}
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
                    selected ? "text-primary-foreground/80" : "text-primary",
                  )}
                >
                  {tr("requested")}
                </span>
              ) : null}
              {!option.is_available ? <span className={CELL_MARKER}>{tr("held")}</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
