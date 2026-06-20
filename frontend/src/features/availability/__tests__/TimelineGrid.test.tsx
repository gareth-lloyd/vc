import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { addDays, parseISO } from "date-fns";
import { renderWithProviders } from "@/test/render";
import type { PropertyListItem } from "@/features/properties/schemas";
import { TimelineGrid } from "../components/TimelineGrid";
import type {
  AvailabilityBookingBand,
  AvailabilityHold,
  WeeklyPrice,
  WeeklyPricesProperty,
} from "../schemas";

// Window anchored on the Sat 13 Jun changeover so weeks land on day 0/7/14.
const windowStart = parseISO("2026-06-13");
const days = Array.from({ length: 21 }, (_, i) => addDays(windowStart, i));

const villa = (id: number, name: string): PropertyListItem => ({
  id,
  name,
  slug: `villa-${id}`,
  status: "active",
  has_active_ical_feed: false,
});

const week = (
  weekStart: string,
  weekEnd: string,
  price: string | null,
  opts: { projected?: boolean; poa?: boolean } = {},
): WeeklyPrice => ({
  week_start: weekStart,
  week_end: weekEnd,
  price,
  currency_code: "GBP",
  is_projected: opts.projected ?? false,
  is_poa: opts.poa ?? false,
  error_code: opts.poa ? "no_rate_available" : null,
});

const booking = (property: number, from: string, to: string): AvailabilityBookingBand => ({
  id: property * 10,
  property,
  date_from: from,
  date_to: to,
  status: "deposit_paid",
  reference: `VC${property}`,
  guest_name: "Guest",
});

const hold = (property: number, from: string, to: string): AvailabilityHold => ({
  id: property * 100,
  property,
  date_from: from,
  date_to: to,
  reason: "owner_block",
});

const weeklyPrices: WeeklyPricesProperty[] = [
  {
    property_id: 1,
    changeover_day: "sat",
    weeks: [
      week("2026-06-13", "2026-06-20", "1400.00"),
      week("2026-06-20", "2026-06-27", "1600.00", { projected: true }),
      week("2026-06-27", "2026-07-04", "1400.00"), // booked by the band below
    ],
  },
  {
    property_id: 2,
    changeover_day: "sat",
    weeks: [
      week("2026-06-13", "2026-06-20", null, { poa: true }),
      week("2026-06-20", "2026-06-27", "2000.00"), // held by the band below
      week("2026-06-27", "2026-07-04", null), // incomplete pricing
    ],
  },
  // Flexible changeover — deferred, renders no strip.
  { property_id: 3, changeover_day: null, weeks: [] },
];

function renderGrid() {
  return renderWithProviders(
    <TimelineGrid
      days={days}
      windowStart={windowStart}
      properties={[villa(1, "Casa Uno"), villa(2, "Casa Dos"), villa(3, "Casa Tres")]}
      holds={[hold(2, "2026-06-20", "2026-06-23")]}
      bookings={[booking(1, "2026-06-27", "2026-07-04")]}
      weeklyPrices={weeklyPrices}
    />,
  );
}

describe("TimelineGrid weekly price strip", () => {
  it("shows a 'from' headline beside each priced villa, cheapest week first", () => {
    renderGrid();
    expect(screen.getByText("from £1,400/wk")).toBeInTheDocument();
    expect(screen.getByText("from £2,000/wk")).toBeInTheDocument();
  });

  it("marks the changeover weekday once per fixed-changeover villa", () => {
    renderGrid();
    expect(screen.getAllByText("Sat")).toHaveLength(2);
  });

  it("renders free weeks as compact prices, with projected weeks guide-marked", () => {
    renderGrid();
    expect(screen.getByText("£1.4K")).toBeInTheDocument();
    expect(screen.getByText("~£1.6K")).toBeInTheDocument();
  });

  it("greys booked/held weeks instead of advertising a sellable price", () => {
    renderGrid();
    expect(screen.getByText("Booked")).toBeInTheDocument(); // villa 1, week 3
    expect(screen.getByText("On hold")).toBeInTheDocument(); // villa 2, week 2
  });

  it("shows POA and incomplete-pricing markers for unpriced weeks", () => {
    renderGrid();
    expect(screen.getByText("POA")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("anchors each week cell with its changeover date", () => {
    renderGrid();
    // Both fixed villas open on Sat 13 Jun.
    expect(screen.getAllByText("13 Jun")).toHaveLength(2);
  });

  it("renders no strip for a flexible-changeover villa", () => {
    renderGrid();
    expect(screen.getByText("Casa Tres")).toBeInTheDocument();
    // Only the two fixed villas carry a per-week headline.
    expect(screen.getAllByText(/\/wk$/)).toHaveLength(2);
  });
});
