import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { OwnerTab } from "../tabs/OwnerTab";

const BOOKING_ID = 88;

const SAMPLE_OWNER = {
  id: 7,
  first_name: "Olivia",
  last_name: "Owner",
  company: "",
  primary_email: "olivia@example.com",
  primary_phone: null,
  address_line_1: "12 Marina Way",
  address_line_2: "",
};

function bookingFixture(
  overrides: {
    owner?: unknown;
    commission?: unknown;
    pricing_snapshot?: unknown;
    currency_code?: string | null;
  } = {},
) {
  return {
    id: BOOKING_ID,
    reference: "B-OWN-001",
    status: "deposit_paid",
    property: 12,
    agent: null,
    assigned_to: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: 1,
    rental_price: "2000.00",
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
    currency_code: overrides.currency_code === undefined ? "GBP" : overrides.currency_code,
    total: "2000.00",
    night_count: 7,
    pricing_snapshot: overrides.pricing_snapshot ?? {},
    discount: "0.00",
    adjustment: "0.00",
    terms_version: 1,
    terms_accepted_at: "2026-05-01T00:00:00Z",
    payment_method: "card",
    cancel_reason: "",
    cancelled_at: null,
    owner: overrides.owner,
    commission: overrides.commission,
  };
}

function setup(route = `/bookings/${BOOKING_ID}/owner`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="owner" replace />} />
        <Route path="owner" element={<OwnerTab />} />
      </Route>
    </Routes>,
    { route },
  );
}

afterEach(() => {
  server.resetHandlers();
});

describe("OwnerTab", () => {
  it("renders contact FactList with the Name label and skips empty rows", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: "percent", amount: "12.50", note: "" },
          }),
        ),
      ),
    );
    setup();

    expect(await screen.findByText("Olivia Owner")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("olivia@example.com")).toBeInTheDocument();
    // Empty company / phone rows should not render.
    expect(screen.queryByText("Company")).toBeNull();
    expect(screen.queryByText("Phone")).toBeNull();
    expect(screen.getByText("12 Marina Way")).toBeInTheDocument();
  });

  it("renders commission with percent formatter when calculation_type is percent", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: "percent", amount: "12.50", note: "" },
          }),
        ),
      ),
    );
    setup();

    expect(await screen.findByText(/Percent of rental/)).toBeInTheDocument();
    expect(screen.getByText(/12\.50%/)).toBeInTheDocument();
  });

  it("renders commission with money formatter when calculation_type is fixed", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: "fixed", amount: "500.00", note: "Flat fee" },
          }),
        ),
      ),
    );
    setup();

    expect(await screen.findByText(/Fixed amount/)).toBeInTheDocument();
    expect(screen.getAllByText(/£500\.00/).length).toBeGreaterThan(0);
    expect(screen.getByText("Flat fee")).toBeInTheDocument();
  });

  it("renders the no_finance empty state when owner and commission are both null", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(bookingFixture({ owner: null, commission: null })),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getByText(/Finance is not configured/i)).toBeInTheDocument());
  });

  it("renders the no_contact empty state when owner is null but commission is set", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: null,
            commission: { calculation_type: "percent", amount: "10.00", note: "" },
          }),
        ),
      ),
    );
    setup();
    await waitFor(() =>
      expect(screen.getByText(/No owner has been assigned/i)).toBeInTheDocument(),
    );
  });

  it("suppresses the payout section entirely when owner is null", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: null,
            commission: { calculation_type: "percent", amount: "10.00", note: "Group default" },
            pricing_snapshot: { currency_code: "GBP", total: "1690.00" },
          }),
        ),
      ),
    );
    setup();
    await waitFor(() =>
      expect(screen.getByText(/No owner has been assigned/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Owner payout/i)).toBeNull();
    expect(screen.queryByText(/Group default/)).toBeNull();
    expect(screen.queryByText(/Pricing breakdown/i)).toBeNull();
  });

  it("renders no_commission_terms in the payout section when calculation_type/amount/note are all empty", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: null, amount: null, note: "" },
          }),
        ),
      ),
    );
    setup();
    await waitFor(() =>
      expect(screen.getByText(/No commission terms on file/i)).toBeInTheDocument(),
    );
  });

  it("still renders the amount when calculation_type is null but amount is present", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: null, amount: "500.00", note: "Side letter" },
          }),
        ),
      ),
    );
    setup();
    // Match may appear elsewhere on the page (e.g. the booking rail) — we
    // only care that the commission row renders at least once.
    expect((await screen.findAllByText(/£500\.00/)).length).toBeGreaterThan(0);
    expect(screen.getByText("Side letter")).toBeInTheDocument();
    // No "no_commission_terms" empty state when real values are present.
    expect(screen.queryByText(/No commission terms on file/i)).toBeNull();
  });

  it("renders pricing-snapshot components when present", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: SAMPLE_OWNER,
            commission: { calculation_type: "percent", amount: "10.00", note: "" },
            pricing_snapshot: {
              currency_code: "GBP",
              rate_subtotal: "1400.00",
              commission: "140.00",
              tax: "150.00",
              total: "1690.00",
            },
          }),
        ),
      ),
    );
    setup();
    expect(await screen.findByText(/Pricing breakdown/i)).toBeInTheDocument();
    expect(screen.getByText("Rate subtotal")).toBeInTheDocument();
    expect(screen.getByText(/£1,400\.00/)).toBeInTheDocument();
    expect(screen.getByText("Grand total")).toBeInTheDocument();
    expect(screen.getByText(/£1,690\.00/)).toBeInTheDocument();
  });

  it("renders pricing-snapshot components without a currency by falling back to a plain decimal", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            currency_code: null,
            owner: SAMPLE_OWNER,
            commission: { calculation_type: "percent", amount: "10.00", note: "" },
            pricing_snapshot: {
              rate_subtotal: "1400.00",
              total: "1690.00",
            },
          }),
        ),
      ),
    );
    setup();
    expect(await screen.findByText(/Pricing breakdown/i)).toBeInTheDocument();
    // Raw decimals (no currency symbol/code) — the breakdown must not vanish.
    expect(screen.getByText("1,400.00")).toBeInTheDocument();
    expect(screen.getByText("1,690.00")).toBeInTheDocument();
  });

  it("renders a View contact link pointing at /contacts/{id}", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({
            owner: {
              id: 42,
              first_name: "Olivia",
              last_name: "Owner",
              company: "Owner Holdings",
              primary_email: null,
              primary_phone: null,
              address_line_1: "",
              address_line_2: "",
            },
            commission: { calculation_type: "percent", amount: "10.00", note: "" },
          }),
        ),
      ),
    );
    setup();
    const link = await screen.findByRole("link", { name: /View contact/i });
    expect(link).toHaveAttribute("href", "/contacts/42");
  });
});
