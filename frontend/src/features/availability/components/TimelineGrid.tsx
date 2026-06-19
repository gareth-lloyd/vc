import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { format, isToday, isWeekend, parseISO } from "date-fns";
import { Repeat } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { activeLocale } from "@/lib/format/date";
import { formatMoney, formatMoneyCompact, formatMoneyWhole } from "@/lib/format/money";
import { propertyAvailabilityPath } from "@/lib/routes";
import type { PropertyListItem } from "@/features/properties/schemas";
import { assignLanes, bandEdges, bandGeometry } from "../geometry";
import { holdDisplayStatus, bandStatusClasses } from "../status";
import type {
  AvailabilityBookingBand,
  AvailabilityHold,
  WeeklyPrice,
  WeeklyPricesProperty,
} from "../schemas";
import { bandDates, type TimelineBand } from "../bands";
import { BandPopover } from "./BandPopover";

const NAME_COL = "220px";
const LANE_HEIGHT = 28;
const BAND_HEIGHT = 22;
const ROW_PADDING = 6;
// Two stacked lines per cell (changeover date + price/state), so a touch taller
// than the bands.
const PRICE_STRIP_HEIGHT = 30;

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
  // GAP-030 — per-week guide prices, loaded separately; undefined while the
  // (independent) price query is still pending, so the strip just doesn't render.
  weeklyPrices?: WeeklyPricesProperty[];
}

/** A changeover week is unsellable if it overlaps any band on the villa.
 * Half-open: a band ending on the week's changeover day (checkout) frees it.
 * A booking outranks a hold when both touch the same week. */
function weekBlock(week: WeeklyPrice, bands: TimelineBand[]): "booked" | "held" | null {
  let held = false;
  for (const band of bands) {
    const { date_from, date_to } = bandDates(band);
    if (date_from < week.week_end && date_to > week.week_start) {
      if (band.kind === "booking") return "booked";
      held = true;
    }
  }
  return held ? "held" : null;
}

/** The "from £X/wk" headline: the cheapest priced week, whole-number formatted.
 * Null when no week carries a firm/guide price (all POA/incomplete). */
function fromPriceSummary(entry: WeeklyPricesProperty): string | null {
  let best: { amount: number; price: string; currency: string | null } | null = null;
  for (const week of entry.weeks) {
    if (week.price == null) continue;
    const amount = Number(week.price);
    if (!Number.isFinite(amount)) continue;
    if (best == null || amount < best.amount) {
      best = { amount, price: week.price, currency: week.currency_code };
    }
  }
  return best ? formatMoneyWhole(best.price, best.currency) : null;
}

/** The price strip beneath a villa's bands. Each changeover week is marked by a
 * diagonal across its changeover-day column — a guest checks out in the morning,
 * the next checks in that afternoon — with the changeover date plus the week's
 * guide price, POA, or (greyed) booked/held state left-aligned to its right. The
 * exact figure is surfaced on hover. */
function PriceStrip({
  entry,
  bands,
  windowStart,
  dayCount,
}: {
  entry: WeeklyPricesProperty;
  bands: TimelineBand[];
  windowStart: Date;
  dayCount: number;
}) {
  const { t } = useTranslation("availability");
  return (
    <div className="border-border/60 relative border-t" style={{ height: PRICE_STRIP_HEIGHT }}>
      {entry.weeks.map((week) => {
        // Position a container spanning the changeover day → next changeover
        // (clamped to the window). Its first day-column carries the diagonal
        // marker; the date + price sit left-aligned in the remaining days.
        const dayIndex = bandEdges(week.week_start, week.week_start, windowStart).start;
        if (dayIndex < 0 || dayIndex >= dayCount) return null;
        const containerDays = Math.min(dayIndex + 7, dayCount) - dayIndex;
        const dayPct = (1 / containerDays) * 100; // changeover day, as % of the container
        const blocked = weekBlock(week, bands);
        const exact = week.price ? formatMoney(week.price, week.currency_code) : null;
        // Availability wins (a blocked week isn't sellable at any price), then
        // POA, then the figure — guide-marked and muted when projected.
        let label: string;
        let muted = false;
        let title: string | undefined;
        if (blocked) {
          label = t(blocked === "booked" ? "price.week_booked" : "price.week_held");
          muted = true;
          title = exact ?? undefined;
        } else if (week.is_poa) {
          label = t("price.poa");
          muted = true;
        } else if (!week.price) {
          label = t("price.none");
          muted = true;
        } else {
          const compact = formatMoneyCompact(week.price, week.currency_code);
          label = week.is_projected ? t("price.guide_value", { value: compact }) : compact;
          muted = week.is_projected;
          title = week.is_projected ? `${t("price.guide_title")} · ${exact}` : (exact ?? undefined);
        }
        return (
          <div
            key={week.week_start}
            className="absolute inset-y-0"
            style={{
              left: `${(dayIndex / dayCount) * 100}%`,
              width: `${(containerDays / dayCount) * 100}%`,
            }}
            title={title}
          >
            {/* Diagonal "/" across the changeover-day column. */}
            <svg
              aria-hidden
              className="absolute inset-y-0 left-0"
              style={{ width: `${dayPct}%` }}
              viewBox="0 0 10 10"
              preserveAspectRatio="none"
            >
              <line
                x1="0"
                y1="10"
                x2="10"
                y2="0"
                className="stroke-border"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div
              className={cn(
                "absolute inset-y-0 right-0 flex flex-col justify-center gap-0.5 truncate pl-1 text-left tabular-nums",
                muted ? "text-muted-foreground" : "text-foreground",
              )}
              style={{ left: `${dayPct}%` }}
            >
              <span className="text-muted-foreground/80 text-[9px] leading-none">
                {fmtShort(week.week_start)}
              </span>
              <span className={cn("text-[11px] leading-none", blocked && "italic")}>{label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
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
  weeklyPrices,
}: TimelineGridProps) {
  const { t } = useTranslation("availability");
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

  const pricesByProperty = useMemo(() => {
    const map = new Map<number, WeeklyPricesProperty>();
    for (const entry of weeklyPrices ?? []) map.set(entry.property_id, entry);
    return map;
  }, [weeklyPrices]);

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
        {properties.map((property, index) => {
          // Subtle zebra striping, alternating by villa, so a villa's bands and
          // its price strip read as one row. Opaque tokens (card = white,
          // muted = neutral-100) keep the sticky name column masking
          // horizontally-scrolled bands.
          const rowBg = index % 2 === 1 ? "bg-muted" : "bg-card";
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
          const priceEntry = pricesByProperty.get(property.id);
          // The changeover weekday, shown once per row. Locale-formatted from
          // the first priced week so it can't drift from the codes the prices
          // are anchored on; absent for flexible-changeover villas (no strip).
          const changeoverLabel =
            priceEntry?.changeover_day && priceEntry.weeks[0]
              ? format(parseISO(priceEntry.weeks[0].week_start), "EEE", { locale: activeLocale() })
              : null;
          // Headline guide price shown beside the name, so the per-week strip
          // below carries detail rather than the same number repeated.
          const fromSummary = priceEntry ? fromPriceSummary(priceEntry) : null;
          return (
            <div
              key={property.id}
              className={cn("border-border/60 grid border-b last:border-b-0", rowBg)}
              style={{ gridTemplateColumns: `${NAME_COL} 1fr` }}
            >
              <div
                className={cn(
                  "sticky left-0 z-10 flex flex-col justify-start gap-0.5 px-3 py-1.5",
                  rowBg,
                )}
              >
                <Link
                  to={villaCalendarPath(property)}
                  className="truncate text-sm font-medium hover:underline"
                >
                  {property.display_name || property.name}
                </Link>
                {changeoverLabel ? (
                  <span className="text-muted-foreground flex items-center gap-1 truncate text-xs">
                    <Repeat className="size-3 shrink-0" aria-label={t("price.changeover_aria")} />
                    <span className="shrink-0">{changeoverLabel}</span>
                    {fromSummary ? (
                      <>
                        <span aria-hidden className="bg-border h-3 w-px shrink-0" />
                        <span className="truncate">
                          {t("price.from_per_week", { value: fromSummary })}
                        </span>
                      </>
                    ) : null}
                  </span>
                ) : null}
              </div>
              <div>
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
                {priceEntry && priceEntry.weeks.length > 0 ? (
                  <PriceStrip
                    entry={priceEntry}
                    bands={bands}
                    windowStart={windowStart}
                    dayCount={days.length}
                  />
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
