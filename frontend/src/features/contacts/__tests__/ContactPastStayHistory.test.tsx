import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactPastStayHistory } from "../components/ContactPastStayHistory";

const STAYS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      booking_number: "BN123",
      villa_name: "Yeraki",
      property: 10,
      property_name: "Villa Yeraki",
      destination: "Corfu",
      year: 2023,
      notes: "",
      date_from: null,
      date_to: null,
      amount: null,
      currency_code: null,
    },
    {
      id: 2,
      booking_number: "",
      villa_name: "Casa Nowhere",
      property: null,
      property_name: null,
      destination: "",
      year: null,
      notes: "CANCELLED",
      date_from: null,
      date_to: null,
      amount: null,
      currency_code: null,
    },
  ],
};

describe("ContactPastStayHistory", () => {
  it("is collapsed by default and reveals stay rows on expand", async () => {
    server.use(http.get("/api/v1/contacts/55/past-stays", () => HttpResponse.json(STAYS)));

    renderWithProviders(<ContactPastStayHistory contactId={55} />);

    expect(await screen.findByText(/imported bookings \(2\)/i)).toBeInTheDocument();
    expect(screen.queryByText("Villa Yeraki")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /toggle imported bookings/i }));

    // A linked stay shows the resolved property name (as a link) + destination.
    expect(await screen.findByRole("link", { name: "Villa Yeraki" })).toHaveAttribute(
      "href",
      "/properties/10",
    );
    expect(screen.getByText("Corfu")).toBeInTheDocument();
    expect(screen.getByText(/2023 · BN123/)).toBeInTheDocument();
    // An unlinked stay falls back to the sheet's villa text and "Year unknown".
    expect(screen.getByText("Casa Nowhere")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Casa Nowhere" })).not.toBeInTheDocument();
    expect(screen.getByText(/year unknown/i)).toBeInTheDocument();
  });

  it("shows exact dates and the recorded amount for archive-dated stays", async () => {
    const base = STAYS.results[1];
    server.use(
      http.get("/api/v1/contacts/56/past-stays", () =>
        HttpResponse.json({
          count: 2,
          next: null,
          previous: null,
          results: [
            {
              ...base,
              id: 3,
              villa_name: "Villa Dated",
              booking_number: "BN1067a",
              year: 2025,
              date_from: "2025-08-03",
              date_to: "2025-08-10",
              amount: "4250.00",
              currency_code: "GBP",
            },
            {
              ...base,
              id: 4,
              villa_name: "Villa No Currency",
              year: 2024,
              date_from: "2024-06-01",
              date_to: "2024-06-08",
              amount: "1800.00",
              currency_code: null,
            },
          ],
        }),
      ),
    );

    renderWithProviders(<ContactPastStayHistory contactId={56} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle imported bookings/i }));

    // Dates replace the bare year; the amount carries its currency when known…
    expect(await screen.findByText(/3–10 Aug 2025 · BN1067a/)).toBeInTheDocument();
    expect(screen.queryByText(/^2025/)).not.toBeInTheDocument();
    expect(screen.getByText("£4,250.00 as recorded")).toBeInTheDocument();
    // …and is a plain number when legacy recorded no currency (never guessed).
    expect(screen.getByText(/1–8 Jun 2024/)).toBeInTheDocument();
    expect(screen.getByText("1,800.00 as recorded")).toBeInTheDocument();
  });

  it("shows no amount for stays without one", async () => {
    server.use(http.get("/api/v1/contacts/57/past-stays", () => HttpResponse.json(STAYS)));

    renderWithProviders(<ContactPastStayHistory contactId={57} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle imported bookings/i }));

    expect(await screen.findByText("Casa Nowhere")).toBeInTheDocument();
    expect(screen.queryByText(/as recorded/i)).not.toBeInTheDocument();
  });

  it("shows the empty state when the contact has no imported bookings", async () => {
    server.use(
      http.get("/api/v1/contacts/77/past-stays", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );

    renderWithProviders(<ContactPastStayHistory contactId={77} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle imported bookings/i }));

    expect(await screen.findByText(/no imported bookings on record/i)).toBeInTheDocument();
  });

  it("surfaces a 'more not shown' hint when the page is truncated", async () => {
    server.use(
      http.get("/api/v1/contacts/55/past-stays", () =>
        HttpResponse.json({
          count: 5,
          next: "http://x/next",
          previous: null,
          results: STAYS.results,
        }),
      ),
    );

    renderWithProviders(<ContactPastStayHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle imported bookings/i }));

    await waitFor(() =>
      expect(screen.getByText(/3 more imported bookings not shown/i)).toBeInTheDocument(),
    );
  });
});
