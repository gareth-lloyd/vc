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
}

/**
 * One positioned band. No in-band text — at year scale a week is ~2% wide, so
 * bands are colour-coded (by price tier / mandatory-ness, see `bandToneClass`)
 * and reveal their detail on hover or keyboard focus. Returns null when the
 * band lies entirely outside the window.
 */
export function TimelineBand({ band, windowStart, dayCount }: TimelineBandProps) {
  const { t } = useTranslation("properties");
  const geometry = bandGeometry(band.dateFrom, band.dateTo, windowStart, dayCount);
  if (!geometry) return null;

  const label = bandTitle(band, t);

  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          aria-label={t("rate_workbench.band.aria", {
            label,
            from: formatDate(band.dateFrom),
            to: formatDate(band.dateTo),
          })}
          className={cn(
            "focus-visible:ring-ring absolute min-w-[6px] rounded-sm border focus-visible:ring-2 focus-visible:outline-none",
            bandToneClass(band),
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
        <BandDetail band={band} />
      </HoverCardContent>
    </HoverCard>
  );
}
