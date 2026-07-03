import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactBookingHistory } from "../components/ContactBookingHistory";

const BOOKINGS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      reference: "VC1234",
      status: "deposit_paid",
      property: 10,
      date_from: "2026-06-10",
      date_to: "2026-06-17",
      adults: 2,
      children: 0,
      is_archived: false,
      created_at: "2026-05-01T00:00:00Z",
    },
    {
      id: 2,
      reference: "VC0099",
      status: "checked_out",
      property: 11,
      date_from: "2025-08-01",
      date_to: "2025-08-08",
      adults: 4,
      children: 1,
      is_archived: false,
      created_at: "2025-07-01T00:00:00Z",
    },
  ],
};

describe("ContactBookingHistory", () => {
  it("is collapsed by default and reveals booking rows on expand", async () => {
    server.use(http.get("/api/v1/contacts/55/bookings", () => HttpResponse.json(BOOKINGS)));

    renderWithProviders(<ContactBookingHistory contactId={55} />);

    expect(await screen.findByText(/previous bookings \(2\)/i)).toBeInTheDocument();
    expect(screen.queryByText("VC1234")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /toggle previous bookings/i }));

    expect(await screen.findByText("VC1234")).toBeInTheDocument();
    expect(screen.getByText("VC0099")).toBeInTheDocument();
    // Status uses the real booking-status label, not the raw value.
    expect(screen.getByText(/deposit paid/i)).toBeInTheDocument();
  });

  it("links each booking reference to its overview page", async () => {
    server.use(http.get("/api/v1/contacts/55/bookings", () => HttpResponse.json(BOOKINGS)));

    renderWithProviders(<ContactBookingHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle previous bookings/i }));

    await screen.findByText("VC1234");
    expect(screen.getByRole("link", { name: "VC1234" })).toHaveAttribute(
      "href",
      "/bookings/1/overview",
    );
    expect(screen.getByRole("link", { name: "VC0099" })).toHaveAttribute(
      "href",
      "/bookings/2/overview",
    );
  });

  it("shows the empty state when the contact has no bookings", async () => {
    server.use(
      http.get("/api/v1/contacts/77/bookings", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );

    renderWithProviders(<ContactBookingHistory contactId={77} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle previous bookings/i }));

    expect(await screen.findByText(/no previous bookings/i)).toBeInTheDocument();
  });

  it("surfaces a 'more not shown' hint when the page is truncated", async () => {
    server.use(
      http.get("/api/v1/contacts/55/bookings", () =>
        HttpResponse.json({
          count: 5,
          next: "http://x/next",
          previous: null,
          results: BOOKINGS.results,
        }),
      ),
    );

    renderWithProviders(<ContactBookingHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle previous bookings/i }));

    await waitFor(() => expect(screen.getByText(/3 more bookings not shown/i)).toBeInTheDocument());
  });
});
