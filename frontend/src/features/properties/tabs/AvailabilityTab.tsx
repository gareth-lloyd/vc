import { useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import {
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  addMonths,
  subMonths,
  format,
  isSameMonth,
  parseISO,
} from "date-fns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { usePropertyHolds, usePropertyBookingsForRange } from "../hooks";
import type { AvailabilityHold, PropertyBookingItem, PropertyDetail } from "../schemas";

interface AvailabilityContext {
  property: PropertyDetail;
}

type CellKind = "available" | "booked" | "held";

interface CellStatus {
  kind: CellKind;
  bookingId?: number;
  holdReason?: string;
}

const HOLD_REASON_LABELS: Record<string, string> = {
  quotation_open: "Quotation open",
  booking_deposit_pending: "Deposit pending",
  owner_block: "Owner block",
  maintenance: "Maintenance",
  manual: "Manual hold",
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

function buildCellMap(
  days: Date[],
  bookings: PropertyBookingItem[],
  holds: AvailabilityHold[],
): Map<string, CellStatus> {
  const map = new Map<string, CellStatus>();
  const isoKeys = days.map((d) => format(d, "yyyy-MM-dd"));

  for (const iso of isoKeys) {
    map.set(iso, { kind: "available" });
  }

  for (const hold of holds) {
    const from = parseISO(hold.date_from);
    const to = parseISO(hold.date_to);
    for (let i = 0; i < days.length; i++) {
      if (days[i] >= from && days[i] < to) {
        map.set(isoKeys[i], { kind: "held", holdReason: hold.reason });
      }
    }
  }

  for (const booking of bookings) {
    const from = parseISO(booking.date_from);
    const to = parseISO(booking.date_to);
    for (let i = 0; i < days.length; i++) {
      if (days[i] >= from && days[i] < to) {
        map.set(isoKeys[i], { kind: "booked", bookingId: booking.id });
      }
    }
  }

  return map;
}

function cellClasses(kind: CellKind, inMonth: boolean): string {
  const base = "flex h-10 w-full items-center justify-center rounded text-sm transition-colors";
  if (!inMonth) return `${base} text-muted-foreground/40`;
  switch (kind) {
    case "booked":
      return `${base} bg-primary text-primary-foreground font-medium`;
    case "held":
      return `${base} bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200 font-medium`;
    default:
      return `${base} text-foreground`;
  }
}

export function AvailabilityTab() {
  const { property } = useOutletContext<AvailabilityContext>();
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(new Date()));

  const { windowStart, windowEnd, days } = useMemo(() => {
    const ws = startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 });
    const we = endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 });
    return { windowStart: ws, windowEnd: we, days: eachDayOfInterval({ start: ws, end: we }) };
  }, [viewMonth]);

  const from = format(windowStart, "yyyy-MM-dd");
  const to = format(windowEnd, "yyyy-MM-dd");

  const holds = usePropertyHolds(property.id, from, to);
  const bookings = usePropertyBookingsForRange(property.id, from, to);

  const cellMap = useMemo(
    () => buildCellMap(days, bookings.data?.results ?? [], holds.data ?? []),
    [days, bookings.data, holds.data],
  );

  const isLoading = holds.isLoading || bookings.isLoading;
  const isError = holds.isError || bookings.isError;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setViewMonth((m) => subMonths(m, 1))}
            aria-label="Previous month"
          >
            &#x25C0;
          </Button>
          <h2 className="text-foreground min-w-[140px] text-center text-base font-semibold">
            {format(viewMonth, "MMMM yyyy")}
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setViewMonth((m) => addMonths(m, 1))}
            aria-label="Next month"
          >
            &#x25B6;
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setViewMonth(startOfMonth(new Date()))}>
          Today
        </Button>
      </div>

      <div className="flex gap-4 text-xs">
        <span className="flex items-center gap-1">
          <span className="border-border inline-block h-3 w-3 rounded border" /> Available
        </span>
        <span className="flex items-center gap-1">
          <span className="bg-primary inline-block h-3 w-3 rounded" /> Booked
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-amber-100 dark:bg-amber-900/30" /> On
          hold
        </span>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : isError ? (
        <ErrorState
          title="Couldn't load availability"
          description="Try again."
          onRetry={() => {
            holds.refetch();
            bookings.refetch();
          }}
        />
      ) : (
        <div className="grid grid-cols-7 gap-1">
          {WEEKDAYS.map((d) => (
            <div
              key={d}
              className="text-muted-foreground flex h-8 items-center justify-center text-xs font-medium"
            >
              {d}
            </div>
          ))}
          {days.map((day) => {
            const iso = format(day, "yyyy-MM-dd");
            const inMonth = isSameMonth(day, viewMonth);
            const cell = cellMap.get(iso) ?? { kind: "available" as const };

            if (!inMonth) {
              return (
                <div key={iso} className={cellClasses("available", false)}>
                  {format(day, "d")}
                </div>
              );
            }

            if (cell.kind === "booked" && cell.bookingId != null) {
              return (
                <Link
                  key={iso}
                  to={`/bookings/${cell.bookingId}`}
                  className={cellClasses("booked", true)}
                  title="Booked"
                >
                  {format(day, "d")}
                </Link>
              );
            }

            if (cell.kind === "held") {
              const label = HOLD_REASON_LABELS[cell.holdReason ?? ""] ?? cell.holdReason ?? "Hold";
              return (
                <div
                  key={iso}
                  className={cellClasses("held", true)}
                  title={label}
                  aria-label={`${format(day, "d MMMM")}: ${label}`}
                >
                  {format(day, "d")}
                </div>
              );
            }

            return (
              <div key={iso} className={cellClasses("available", true)}>
                {format(day, "d")}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
