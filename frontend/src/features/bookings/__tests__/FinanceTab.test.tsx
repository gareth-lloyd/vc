import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { FinanceTab } from "../tabs/FinanceTab";

const BOOKING_ID = 91;

function bookingFixture(pricing_snapshot: unknown) {
  return {
    id: BOOKING_ID,
    reference: "B-FIN-001",
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
    rental_price: "2500.00",
    balance_due: "1500.00",
    balance_due_at: "2026-06-01",
    site_source: "main_website",
    is_archived: false,
    archived_at: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-02T00:00:00Z",
    property_name: "Casa Norte",
    guest_name: "Ada Lovelace",
    guest_email: "ada@example.com",
    currency_code: "GBP",
    total: "2500.00",
    night_count: 7,
    pricing_snapshot,
    discount: "0.00",
    adjustment: "0.00",
    terms_version: 1,
    terms_accepted_at: "2026-05-01T00:00:00Z",
    payment_method: "card",
    cancel_reason: "",
    cancelled_at: null,
  };
}

function setup(route = `/bookings/${BOOKING_ID}/finance`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="finance" replace />} />
        <Route path="finance" element={<FinanceTab />} />
      </Route>
    </Routes>,
    { route },
  );
}

afterEach(() => {
  server.resetHandlers();
});

describe("FinanceTab", () => {
  beforeEach(() => {
    // Default: handler set per-test
  });

  it("renders snapshot fact rows when pricing_snapshot is populated", async () => {
    const snapshot = {
      currency_code: "GBP",
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      nights: 7,
      rate_subtotal: "1400.00",
      extras_total: "100.00",
      tax: "150.00",
      commission: "200.00",
      total: "1850.00",
      lines: [
        { label: "Base rate", quantity: 7, unit_price: "200.00", total: "1400.00" },
        { label: "Cleaning", quantity: 1, unit_price: "100.00", total: "100.00" },
      ],
    };
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(snapshot))),
    );
    setup();

    expect(await screen.findByRole("heading", { name: "Finance" })).toBeInTheDocument();
    expect(screen.getByText("Rate subtotal")).toBeInTheDocument();
    expect(screen.getAllByText(/£1,400\.00 GBP/).length).toBeGreaterThan(0);
    expect(screen.getByText("Grand total")).toBeInTheDocument();
    expect(screen.getByText(/£1,850\.00 GBP/)).toBeInTheDocument();
  });

  it("renders the lines table when pricing_snapshot has lines", async () => {
    const snapshot = {
      currency_code: "GBP",
      rate_subtotal: "100.00",
      total: "100.00",
      lines: [{ label: "Base rate", quantity: 1, unit_price: "100.00", total: "100.00" }],
    };
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(snapshot))),
    );
    setup();
    expect(await screen.findByText("Line items")).toBeInTheDocument();
    expect(screen.getByText("Base rate")).toBeInTheDocument();
  });

  it("renders the line-item-editing alert", async () => {
    const snapshot = { currency_code: "GBP", total: "100.00" };
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(snapshot))),
    );
    setup();
    expect(await screen.findByText(/Line-item editing coming/i)).toBeInTheDocument();
  });

  it("shows an empty state when pricing_snapshot is missing", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(null))),
    );
    setup();
    await waitFor(() =>
      expect(screen.getByText(/Pricing snapshot not available/i)).toBeInTheDocument(),
    );
  });

  it("shows an empty state when pricing_snapshot is an empty object", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
    );
    setup();
    await waitFor(() =>
      expect(screen.getByText(/Pricing snapshot not available/i)).toBeInTheDocument(),
    );
  });
});
