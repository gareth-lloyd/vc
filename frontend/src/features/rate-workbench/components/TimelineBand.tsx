import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { bandGeometry } from "@/lib/timeline/geometry";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { bandTitle, type WorkbenchBand } from "../toLanes";
import { BAND_HEIGHT, bandToneClass, bandTop } from "./timelineLayout";
import { BandDetail } from "./BandDetail";

interface TimelineBandProps {
  band: WorkbenchBand;
  windowStart: Date;
  dayCount: number;
  /** Coverage gaps only: a click creates a period over the gap. Passing this
   * IS the write affordance — omit it for read-only users. */
  onGapClick?: (gap: { from: string; to: string }) => void;
  /** Rates lane only: a hover-revealed "+" at the band's right edge creates a
   * period starting the day after this one. Same contract as `onGapClick` —
   * the handler is the affordance, omit it for read-only users. */
  onAddAfter?: (dateFrom: string) => void;
}

/**
 * One positioned band. No in-band text — at year scale a week is ~2% wide, so
 * bands are colour-coded (by price tier / mandatory-ness, see `bandToneClass`)
 * and reveal their detail on hover or keyboard focus. Returns null when the
 * band lies entirely outside the window.
 */
export function TimelineBand({
  band,
  windowStart,
  dayCount,
  onGapClick,
  onAddAfter,
}: TimelineBandProps) {
  const { t } = useTranslation("properties");
  const geometry = bandGeometry(band.dateFrom, band.dateToExclusive, windowStart, dayCount);
  if (!geometry) return null;

  const dates = { from: formatDate(band.dateFrom), to: formatDate(band.dateTo) };
  const gapClickable = !!band.meta.isGap && !!onGapClick;
  const addable = band.laneKey === "rates" && !!onAddAfter;
  const positionStyle = {
    left: `${geometry.leftPct}%`,
    width: `${geometry.widthPct}%`,
    top: bandTop(band.sublane),
    height: BAND_HEIGHT,
  };

  const bandButton = (
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
            gapClickable ? () => onGapClick({ from: band.dateFrom, to: band.dateTo }) : undefined
          }
          className={cn(
            "focus-visible:ring-ring absolute min-w-[6px] rounded-sm border focus-visible:ring-2 focus-visible:outline-none",
            addable && "inset-0",
            bandToneClass(band),
            gapClickable ? "cursor-pointer" : "cursor-default",
          )}
          style={addable ? undefined : positionStyle}
        />
      </HoverCardTrigger>
      <HoverCardContent align="start">
        <BandDetail band={band} showGapAction={gapClickable} />
      </HoverCardContent>
    </HoverCard>
  );

  if (!addable) return bandButton;

  // The "+" can't nest inside the band <button>, so a positioned `group`
  // wrapper takes the geometry and the two become siblings; the "+" sits on
  // the band's end edge and reveals on hover (or its own keyboard focus).
  return (
    <div className="group absolute min-w-[6px]" style={positionStyle}>
      {bandButton}
      <button
        type="button"
        aria-label={t("rate_workbench.band.add_after_aria", {
          date: formatDate(band.dateToExclusive),
        })}
        onClick={() => onAddAfter(band.dateToExclusive)}
        className="bg-primary text-primary-foreground focus-visible:ring-ring absolute top-1/2 -right-2 z-10 flex size-4 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:outline-none"
      >
        <Plus className="size-3" aria-hidden />
      </button>
    </div>
  );
}
