import { useTranslation } from "react-i18next";
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
}

/**
 * One positioned band. No in-band text — at year scale a week is ~2% wide, so
 * bands are colour-coded (by price tier / mandatory-ness, see `bandToneClass`)
 * and reveal their detail on hover or keyboard focus. Returns null when the
 * band lies entirely outside the window.
 */
export function TimelineBand({ band, windowStart, dayCount, onGapClick }: TimelineBandProps) {
  const { t } = useTranslation("properties");
  const geometry = bandGeometry(band.dateFrom, band.dateToExclusive, windowStart, dayCount);
  if (!geometry) return null;

  const dates = { from: formatDate(band.dateFrom), to: formatDate(band.dateTo) };
  const gapClickable = !!band.meta.isGap && !!onGapClick;

  return (
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
            bandToneClass(band),
            gapClickable ? "cursor-pointer" : "cursor-default",
          )}
          style={{
            left: `${geometry.leftPct}%`,
            width: `${geometry.widthPct}%`,
            top: bandTop(band.sublane),
            height: BAND_HEIGHT,
          }}
        />
      </HoverCardTrigger>
      <HoverCardContent align="start">
        <BandDetail band={band} showGapAction={gapClickable} />
      </HoverCardContent>
    </HoverCard>
  );
}
