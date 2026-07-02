import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { bandEdges, bandGeometry } from "@/lib/timeline/geometry";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { bandTitle, type WorkbenchBand } from "../toLanes";
import { BAND_HEIGHT, bandToneClass, bandTop } from "./timelineLayout";
import { BandDetail } from "./BandDetail";

/** Prefill handed to the page's period-create dialog by either timeline write
 * affordance. `planId` names the plan to create under; when absent the page
 * falls back to the matrix's selected plan. */
export interface CreatePeriodPrefill {
  planId?: number;
  date_from: string;
  date_to?: string;
}

interface TimelineBandProps {
  band: WorkbenchBand;
  windowStart: Date;
  dayCount: number;
  /** The single write affordance: coverage-gap bands become clickable (create
   * a period over the gap) and rates bands grow a hover-revealed "+" (create
   * a period in the free range after them, under their own plan, per
   * `band.meta.addAfter`). Passing this IS the affordance — omit it for
   * read-only users. */
  onCreatePeriod?: (prefill: CreatePeriodPrefill) => void;
}

/**
 * One positioned band. No in-band text — at year scale a week is ~2% wide, so
 * bands are colour-coded (by price tier / mandatory-ness, see `bandToneClass`)
 * and reveal their detail on hover or keyboard focus. A band clipped by the
 * year window squares off and marks the clipped edge with a chevron — the
 * period continues into the neighbouring year (true dates live in the hover
 * card and accessible name). Returns null when the band lies entirely outside
 * the window.
 */
export function TimelineBand({ band, windowStart, dayCount, onCreatePeriod }: TimelineBandProps) {
  const { t } = useTranslation("properties");
  const geometry = bandGeometry(band.dateFrom, band.dateToExclusive, windowStart, dayCount);
  if (!geometry) return null;

  const dates = { from: formatDate(band.dateFrom), to: formatDate(band.dateTo) };
  const gapClickable = !!band.meta.isGap && !!onCreatePeriod;
  const addPrefill =
    band.laneKey === "rates" && onCreatePeriod && band.meta.planId != null && band.meta.addAfter
      ? { planId: band.meta.planId, ...band.meta.addAfter }
      : undefined;
  const edges = bandEdges(band.dateFrom, band.dateToExclusive, windowStart);
  const continuesStart = edges.start < 0;
  const continuesEnd = edges.end > dayCount;

  return (
    <div
      className="group absolute min-w-[6px]"
      style={{
        left: `${geometry.leftPct}%`,
        width: `${geometry.widthPct}%`,
        top: bandTop(band.sublane),
        height: BAND_HEIGHT,
      }}
    >
      <HoverCard openDelay={150} closeDelay={100}>
        <HoverCardTrigger asChild>
          <button
            type="button"
            // A clickable gap's accessible name must promise the action, not
            // just the information — the hover card is pointer-only.
            aria-label={
              gapClickable
                ? t("rate_workbench.coverage.gap_aria_action", dates)
                : t("rate_workbench.band.aria", { label: bandTitle(band, t), ...dates })
            }
            onClick={
              gapClickable
                ? () =>
                    onCreatePeriod?.({
                      planId: band.meta.planId,
                      date_from: band.dateFrom,
                      date_to: band.dateTo,
                    })
                : undefined
            }
            className={cn(
              "focus-visible:ring-ring absolute inset-0 overflow-hidden rounded-sm border focus-visible:ring-2 focus-visible:outline-none",
              continuesStart && "rounded-l-none",
              continuesEnd && "rounded-r-none",
              bandToneClass(band),
              gapClickable ? "cursor-pointer" : "cursor-default",
            )}
          >
            {continuesStart ? (
              <ChevronLeft
                data-testid="band-continues-start"
                aria-hidden
                className="text-foreground/70 absolute top-1/2 left-0 size-3 -translate-y-1/2"
              />
            ) : null}
            {continuesEnd ? (
              <ChevronRight
                data-testid="band-continues-end"
                aria-hidden
                className="text-foreground/70 absolute top-1/2 right-0 size-3 -translate-y-1/2"
              />
            ) : null}
          </button>
        </HoverCardTrigger>
        <HoverCardContent align="start">
          <BandDetail band={band} showGapAction={gapClickable} />
        </HoverCardContent>
      </HoverCard>
      {/* The "+" can't nest inside the band <button>, so it's a sibling: it
        sits on the band's end edge and reveals on hover (or its own keyboard
        focus). */}
      {addPrefill ? (
        <button
          type="button"
          aria-label={t("rate_workbench.band.add_after_aria", {
            date: formatDate(addPrefill.date_from),
          })}
          onClick={() => onCreatePeriod?.(addPrefill)}
          className="bg-primary text-primary-foreground focus-visible:ring-ring absolute top-1/2 -right-2 z-10 flex size-4 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:outline-none"
        >
          <Plus className="size-3" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}
