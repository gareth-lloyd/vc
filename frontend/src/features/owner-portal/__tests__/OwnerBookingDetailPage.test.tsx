import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { OwnerBookingDetailPage } from "../OwnerBookingDetailPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function booking(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    reference: "VC-0007",
    status: "deposit_paid",
    property_id: 3,
    property_name: "Villa Anemoi",
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency_code: "EUR",
    guest_name: "Ada Lovelace",
    guest_country: { code: "GB", name: "United Kingdom" },
    is_repeat_guest: false,
    can_approve: false,
    ...overrides,
  };
}

// A granted (view_full_money) booking: whole-booking money + per-component splits.
const moneyFields = {
  gross_total: "2500.00",
  commission: "500.00",
  net_to_owner: "1875.00",
};

// Midday timestamps keep formatDate TZ-robust (midnight-UTC renders a day
// early west of UTC).
const depositSplit = {
  purpose: "deposit",
  status: "succeeded",
  due_at: "2026-05-15T12:00:00Z",
  gross: "1000.00",
  commission: "200.00",
  tax: "50.00",
  net_to_owner: "750.00",
};
const balanceSplit = {
  purpose: "balance",
  status: "pending",
  due_at: "2026-06-01T12:00:00Z",
  gross: "1500.00",
  commission: "300.00",
  tax: "75.00",
  net_to_owner: "1125.00",
};

function mockBooking(overrides: Record<string, unknown> = {}) {
  server.use(http.get("/api/v1/owner/bookings/7", () => HttpResponse.json(booking(overrides))));
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/owner/bookings/:id" element={<OwnerBookingDetailPage />} />
    </Routes>,
    { route: "/owner/bookings/7" },
  );
}

afterEach(() => server.resetHandlers());

describe("Owner booking detail — payment schedule", () => {
  it("renders per-component splits with formatted money when payment_splits is present", async () => {
    mockBooking({ ...moneyFields, payment_splits: [depositSplit, balanceSplit] });
    renderPage();

    const heading = await screen.findByText("Payment schedule");
    const section = within(heading.closest("section")!);

    // Deposit component: figures + due date; succeeded ⇒ no waived marker.
    const deposit = within(section.getByTestId("payment-split-deposit"));
    expect(deposit.getByText("Deposit")).toBeInTheDocument();
    expect(deposit.getByText("Due 15 May 2026")).toBeInTheDocument();
    expect(deposit.getByText("€1,000.00")).toBeInTheDocument();
    expect(deposit.getByText("€200.00")).toBeInTheDocument();
    expect(deposit.getByText("€50.00")).toBeInTheDocument();
    expect(deposit.getByText("€750.00")).toBeInTheDocument();
    expect(deposit.queryByText("Waived")).not.toBeInTheDocument();

    // Balance component.
    const balance = within(section.getByTestId("payment-split-balance"));
    expect(balance.getByText("Balance")).toBeInTheDocument();
    expect(balance.getByText("Due 1 Jun 2026")).toBeInTheDocument();
    expect(balance.getByText("€1,500.00")).toBeInTheDocument();
    expect(balance.getByText("€300.00")).toBeInTheDocument();
    expect(balance.getByText("€75.00")).toBeInTheDocument();
    expect(balance.getByText("€1,125.00")).toBeInTheDocument();

    // Commission renders only under an explicit "Commission" label; the net
    // line uses the owner-facing wording.
    expect(deposit.getByText("Commission")).toBeInTheDocument();
    expect(deposit.getByText("Your share")).toBeInTheDocument();
  });

  it("marks a waived component with the muted waived label", async () => {
    mockBooking({
      ...moneyFields,
      payment_splits: [depositSplit, { ...balanceSplit, status: "waived" }],
    });
    renderPage();

    await screen.findByText("Payment schedule");
    const balance = within(screen.getByTestId("payment-split-balance"));
    expect(balance.getByText("Waived")).toBeInTheDocument();
  });

  it("omits the section when payment_splits is absent (no grant / redacted)", async () => {
    // Redacted body: no money keys at all — the money section is absent too.
    mockBooking();
    renderPage();

    await screen.findAllByText("VC-0007");
    expect(screen.queryByText("Payment schedule")).not.toBeInTheDocument();
  });

  it("omits the section when payment_splits is an empty array (money, no schedule)", async () => {
    mockBooking({ ...moneyFields, payment_splits: [] });
    renderPage();

    // Money block still renders...
    expect(await screen.findByText("Gross total")).toBeInTheDocument();
    // ...but there is no schedule to split.
    expect(screen.queryByText("Payment schedule")).not.toBeInTheDocument();
  });
});
