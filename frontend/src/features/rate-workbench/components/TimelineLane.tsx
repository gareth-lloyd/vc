import { useTranslation } from "react-i18next";
import type { LaneModel } from "../toLanes";
import type { MonthTick } from "../yearWindow";
import { TimelineBand } from "./TimelineBand";
import { laneHeight } from "./timelineLayout";

interface TimelineLaneProps {
  lane: LaneModel;
  windowStart: Date;
  dayCount: number;
  ticks: MonthTick[];
  onGapClick?: (gap: { from: string; to: string }) => void;
  onAddAfter?: (dateFrom: string) => void;
}

/** One concern lane: a sticky-left label + a relative band track with month gridlines. */
export function TimelineLane({
  lane,
  windowStart,
  dayCount,
  ticks,
  onGapClick,
  onAddAfter,
}: TimelineLaneProps) {
  const { t } = useTranslation("properties");
  const maxSublane = lane.bands.reduce((m, b) => Math.max(m, b.sublane), 0);

  // The coverage lane names the plan it annotates; an empty coverage lane is
  // GOOD news ("every date priced"), unlike other lanes' neutral "None".
  const label =
    lane.key === "coverage"
      ? t("rate_workbench.lanes.coverage", { plan: lane.planName ?? "" })
      : t(`rate_workbench.lanes.${lane.key}`);
  const emptyText =
    lane.key === "coverage" ? t("rate_workbench.coverage.no_gaps") : t("rate_workbench.lane_empty");

  return (
    <div className="border-border grid grid-cols-[128px_1fr] border-t">
      <div className="text-muted-foreground bg-muted/20 flex items-center px-3 text-xs font-medium">
        {label}
      </div>
      <div className="relative" style={{ height: laneHeight(maxSublane) }}>
        {ticks.map((tick) => (
          <div
            key={tick.key}
            aria-hidden
            className="border-border/40 absolute inset-y-0 border-l"
            style={{ left: `${tick.leftPct}%` }}
          />
        ))}
        {lane.bands.length === 0 ? (
          <span className="text-muted-foreground/50 absolute inset-0 flex items-center pl-2 text-xs">
            {emptyText}
          </span>
        ) : (
          lane.bands.map((band) => (
            <TimelineBand
              key={band.id}
              band={band}
              windowStart={windowStart}
              dayCount={dayCount}
              onGapClick={onGapClick}
              onAddAfter={onAddAfter}
            />
          ))
        )}
      </div>
    </div>
  );
}
