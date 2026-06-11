import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { format, isToday, isWeekend, parseISO } from "date-fns";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { activeLocale } from "@/lib/format/date";
import { propertyAvailabilityPath } from "@/lib/routes";
import type { PropertyListItem } from "@/features/properties/schemas";
import { assignLanes, bandEdges, bandGeometry } from "../geometry";
import { holdDisplayStatus, bandStatusClasses } from "../status";
import type { AvailabilityBookingBand, AvailabilityHold } from "../schemas";
import { bandDates, type TimelineBand } from "../bands";
import { BandPopover } from "./BandPopover";

const NAME_COL = "220px";
const LANE_HEIGHT = 28;
const BAND_HEIGHT = 22;
const ROW_PADDING = 6;

/** Slug-safe villa path (some legacy slugs are full URLs — fall back to id). */
function villaCalendarPath(property: PropertyListItem): string {
  const slug = property.slug?.trim();
  return propertyAvailabilityPath(slug && !slug.includes("/") ? slug : property.id);
}

const fmtShort = (iso: string) => format(parseISO(iso), "d MMM", { locale: activeLocale() });

interface TimelineGridProps {
  days: Date[];
  windowStart: Date;
  properties: PropertyListItem[];
  holds: AvailabilityHold[];
  bookings: AvailabilityBookingBand[];
}

function DayCells({ days }: { days: Date[] }) {
  return (
    <>
      {days.map((day) => (
        <div
          key={day.toISOString()}
          className={cn("border-border/60 border-l", isWeekend(day) && "bg-muted/50")}
        />
      ))}
    </>
  );
}

function RowBands({
  property,
  bands,
  lanes,
  days,
  windowStart,
}: {
  property: PropertyListItem;
  bands: TimelineBand[];
  lanes: number[];
  days: Date[];
  windowStart: Date;
}) {
  const { t } = useTranslation("availability");
  return (
    <>
      {bands.map((band, index) => {
        const { date_from, date_to } = bandDates(band);
        const geometry = bandGeometry(date_from, date_to, windowStart, days.length, {
          halfDayOffset: band.kind === "booking",
        });
        if (!geometry) return null;
        const status =
          band.kind === "booking" ? ("booked" as const) : holdDisplayStatus(band.hold.reason);
        const label =
          band.kind === "booking"
            ? (band.booking.guest_name ?? band.booking.reference)
            : t(`reason_labels.${band.hold.reason}`, band.hold.reason);
        const aria =
          band.kind === "booking"
            ? t("band.booking_aria", {
                reference: band.booking.reference,
                guest: band.booking.guest_name || t("band.no_guest"),
              })
            : t("band.hold_aria", {
                reason: t(`reason_labels.${band.hold.reason}`, band.hold.reason),
                from: fmtShort(date_from),
                to: fmtShort(date_to),
              });
        const key = band.kind === "booking" ? `b-${band.booking.id}` : `h-${band.hold.id}`;
        return (
          <Popover key={key}>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={aria}
                className={cn(
                  "absolute truncate rounded px-1.5 text-left text-xs leading-snug",
                  bandStatusClasses(status),
                )}
                style={{
                  left: `${geometry.leftPct}%`,
                  width: `${geometry.widthPct}%`,
                  top: lanes[index] * LANE_HEIGHT + ROW_PADDING / 2,
                  height: BAND_HEIGHT,
                }}
              >
                {label}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72">
              <BandPopover band={band} villaCalendarPath={villaCalendarPath(property)} />
            </PopoverContent>
          </Popover>
        );
      })}
    </>
  );
}

export function TimelineGrid({
  days,
  windowStart,
  properties,
  holds,
  bookings,
}: TimelineGridProps) {
  const bandsByProperty = useMemo(() => {
    const map = new Map<number, TimelineBand[]>();
    const push = (id: number, band: TimelineBand) => {
      const list = map.get(id) ?? [];
      list.push(band);
      map.set(id, list);
    };
    for (const hold of holds) push(hold.property, { kind: "hold", hold });
    for (const booking of bookings) push(booking.property, { kind: "booking", booking });
    return map;
  }, [holds, bookings]);

  const dayColumns = `repeat(${days.length}, minmax(28px, 1fr))`;

  return (
    <div className="border-border overflow-x-auto rounded-md border">
      <div style={{ minWidth: 220 + days.length * 28 }}>
        {/* Date axis */}
        <div
          className="border-border bg-card sticky top-0 z-10 grid border-b"
          style={{ gridTemplateColumns: `${NAME_COL} ${dayColumns}` }}
        >
          <div className="bg-card sticky left-0 z-10" />
          {days.map((day) => (
            <div
              key={day.toISOString()}
              className={cn(
                "border-border/60 border-l py-1 text-center",
                isWeekend(day) && "bg-muted/50",
              )}
            >
              <div className="text-muted-foreground text-[10px] leading-none">
                {format(day, "EEEEE", { locale: activeLocale() })}
              </div>
              <div
                className={cn(
                  "text-xs",
                  isToday(day) && "text-primary-foreground bg-primary mx-auto w-5 rounded-full",
                )}
              >
                {format(day, "d")}
              </div>
            </div>
          ))}
        </div>

        {/* One row per villa */}
        {properties.map((property) => {
          const bands = bandsByProperty.get(property.id) ?? [];
          const lanes = assignLanes(
            bands.map((band) => {
              const { date_from, date_to } = bandDates(band);
              return bandEdges(date_from, date_to, windowStart, {
                halfDayOffset: band.kind === "booking",
              });
            }),
          );
          const laneCount = bands.length ? Math.max(...lanes) + 1 : 1;
          const rowHeight = laneCount * LANE_HEIGHT + ROW_PADDING;
          return (
            <div
              key={property.id}
              className="border-border/60 grid border-b last:border-b-0"
              style={{ gridTemplateColumns: `${NAME_COL} 1fr` }}
            >
              <div className="bg-card sticky left-0 z-10 flex items-center px-3 py-1.5">
                <Link
                  to={villaCalendarPath(property)}
                  className="truncate text-sm font-medium hover:underline"
                >
                  {property.display_name || property.name}
                </Link>
              </div>
              <div className="relative" style={{ height: rowHeight }}>
                <div
                  className="absolute inset-0 grid"
                  style={{ gridTemplateColumns: dayColumns }}
                  aria-hidden
                >
                  <DayCells days={days} />
                </div>
                <RowBands
                  property={property}
                  bands={bands}
                  lanes={lanes}
                  days={days}
                  windowStart={windowStart}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
