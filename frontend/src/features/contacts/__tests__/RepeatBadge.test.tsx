import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { RepeatBadge } from "../components/RepeatBadge";

describe("RepeatBadge", () => {
  it("renders nothing for a first-time contact", () => {
    renderWithProviders(<RepeatBadge bookingCount={0} pastStayCount={0} isRepeat={false} />);
    expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
  });

  it("shows only the past-stay count for a sheet-imported repeat customer", () => {
    // GAP-089: a customer known only from the historic spreadsheets has no
    // bookings yet — "0 bookings" next to "Repeat" would read as a contradiction.
    renderWithProviders(<RepeatBadge bookingCount={0} pastStayCount={3} isRepeat />);
    expect(screen.getByText("Repeat")).toBeInTheDocument();
    expect(screen.getByText("3 past stays")).toBeInTheDocument();
    expect(screen.queryByText(/bookings?/)).not.toBeInTheDocument();
  });

  it("shows both figures when the customer has bookings and past stays", () => {
    renderWithProviders(<RepeatBadge bookingCount={2} pastStayCount={1} isRepeat />);
    expect(screen.getByText("2 bookings · 1 past stay")).toBeInTheDocument();
  });

  it("keeps the booking-only label unchanged", () => {
    renderWithProviders(<RepeatBadge bookingCount={1} isRepeat />);
    expect(screen.getByText("1 booking")).toBeInTheDocument();
  });
});
