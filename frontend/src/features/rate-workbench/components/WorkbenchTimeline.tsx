import { format } from "date-fns";
import { activeLocale } from "@/lib/format/date";
import type { LaneModel } from "../toLanes";
import { monthTicks } from "../yearWindow";
import { TimelineLane } from "./TimelineLane";

interface WorkbenchTimelineProps {
  lanes: LaneModel[];
  windowStart: Date;
  dayCount: number;
}

/** Whole-year timeline: a month header over six stacked concern lanes. */
export function WorkbenchTimeline({ lanes, windowStart, dayCount }: WorkbenchTimelineProps) {
  const locale = activeLocale();
  const ticks = monthTicks(windowStart, dayCount);

  return (
    <div className="border-border overflow-hidden rounded-md border">
      <div className="border-border bg-muted/40 grid grid-cols-[128px_1fr] border-b">
        <div />
        <div className="relative h-7">
          {ticks.map((tick) => (
            <span
              key={tick.key}
              className="text-muted-foreground absolute top-1.5 text-[10px] font-medium"
              style={{ left: `${tick.leftPct}%` }}
            >
              {format(tick.date, "LLL", { locale })}
            </span>
          ))}
        </div>
      </div>
      {lanes.map((lane) => (
        <TimelineLane
          key={lane.key}
          lane={lane}
          windowStart={windowStart}
          dayCount={dayCount}
          ticks={ticks}
        />
      ))}
    </div>
  );
}
