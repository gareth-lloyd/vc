import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { BookingsListPage } from "../BookingsListPage";

const baseBooking = {
  id: 51,
  reference: "B-AAA-001",
  status: "deposit_paid",
  property: 12,
  guest: 99,
  agent: null,
  assigned_to: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  currency: 1,
  rental_price: "1500.00",
  balance_due: "1000.00",
  balance_due_at: "2026-06-01",
  site_source: "main_website",
  is_archived: false,
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      ...baseBooking,
      property_name: "Casa Norte",
      guest_name: "Ada Lovelace",
      currency_code: "GBP",
      total: "2500.00",
      night_count: 7,
    },
    {
      ...baseBooking,
      id: 52,
      reference: "B-BBB-002",
      status: "checked_in",
      property_name: "Villa Azul",
      guest_name: "Grace Hopper",
      currency_code: "EUR",
      total: "3200.50",
      night_count: 10,
    },
  ],
};

describe("BookingsListPage", () => {
  it("renders rows from /bookings", async () => {
    server.use(http.get("/api/v1/bookings", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/bookings" element={<BookingsListPage />} />
      </Routes>,
      { route: "/bookings" },
    );
    expect(await screen.findByText("B-AAA-001")).toBeInTheDocument();
    expect(screen.getByText("Casa Norte")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("£2,500.00")).toBeInTheDocument();
  });

  it("renders an empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/bookings", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/bookings" element={<BookingsListPage />} />
      </Routes>,
      { route: "/bookings" },
    );
    expect(await screen.findByText(/no bookings match/i)).toBeInTheDocument();
  });

  it("shows an error state on 500 and retries", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/bookings", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/bookings" element={<BookingsListPage />} />
      </Routes>,
      { route: "/bookings" },
    );
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("B-AAA-001")).toBeInTheDocument();
  });

  it("debounces search and forwards q to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/bookings", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("q") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/bookings" element={<BookingsListPage />} />
      </Routes>,
      { route: "/bookings" },
    );
    await screen.findByText("B-AAA-001");
    await userEvent.type(screen.getByLabelText(/search/i), "ada");
    await waitFor(() => expect(seen).toContain("ada"));
  });

  it("navigates to the detail overview on row click", async () => {
    server.use(http.get("/api/v1/bookings", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/bookings" element={<BookingsListPage />} />
        <Route path="/bookings/:id/overview" element={<div>Detail: 51</div>} />
      </Routes>,
      { route: "/bookings" },
    );
    await userEvent.click(await screen.findByText("B-AAA-001"));
    await waitFor(() => expect(screen.getByText("Detail: 51")).toBeInTheDocument());
  });
});
