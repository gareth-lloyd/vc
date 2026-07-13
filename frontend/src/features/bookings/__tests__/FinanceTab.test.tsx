import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { FinanceTab } from "../tabs/FinanceTab";
import type { BookingChargeItem } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const BOOKING_ID = 91;

function bookingFixture(pricing_snapshot: unknown, overrides: Record<string, unknown> = {}) {
  return {
    id: BOOKING_ID,
    reference: "B-FIN-001",
    status: "deposit_paid",
    property: 12,
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
    charges_total: "0.00",
    night_count: 7,
    pricing_snapshot,
    terms_version: 1,
    terms_accepted_at: "2026-05-01T00:00:00Z",
    payment_method: "card",
    cancel_reason: "",
    cancelled_at: null,
    ...overrides,
  };
}

function chargeItem(overrides: Partial<BookingChargeItem> = {}): BookingChargeItem {
  return {
    id: 1,
    booking: BOOKING_ID,
    label: "Late checkout",
    amount: "150.00",
    currency: 1,
    currency_code: "GBP",
    notes: "",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function chargesResponse(items: BookingChargeItem[]) {
  return { count: items.length, next: null, previous: null, results: items };
}

function useCharges(items: BookingChargeItem[]) {
  server.use(
    http.get(`/api/v1/bookings/${BOOKING_ID}/charge-items`, () =>
      HttpResponse.json(chargesResponse(items)),
    ),
  );
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

const baseUser = {
  id: 1,
  email: "writer@example.com",
  first_name: "Wri",
  last_name: "Ter",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  preferred_language: "en",
};

function grantWriterRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: "RESERVATIONS" },
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function clearRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: null },
    role: null,
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

beforeEach(() => {
  grantWriterRole();
});

afterEach(() => {
  server.resetHandlers();
  clearRole();
});

describe("FinanceTab — pricing snapshot", () => {
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
    useCharges([]);
    setup();

    expect(await screen.findByRole("heading", { name: "Finance" })).toBeInTheDocument();
    expect(screen.getByText("Rate subtotal")).toBeInTheDocument();
    expect(screen.getAllByText(/£1,400\.00/).length).toBeGreaterThan(0);
    expect(screen.getByText("Grand total")).toBeInTheDocument();
    expect(screen.getByText(/£1,850\.00/)).toBeInTheDocument();
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
    useCharges([]);
    setup();
    expect(await screen.findByText("Line items")).toBeInTheDocument();
    expect(screen.getByText("Base rate")).toBeInTheDocument();
  });

  it("renders the snapshot-immutable note instead of the old coming-soon alert", async () => {
    const snapshot = { currency_code: "GBP", total: "100.00" };
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(snapshot))),
    );
    useCharges([]);
    setup();
    expect(await screen.findByText(/fixed at confirmation/i)).toBeInTheDocument();
    expect(screen.queryByText(/Line-item editing coming/i)).not.toBeInTheDocument();
  });

  it("shows the snapshot empty state when pricing_snapshot is missing", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture(null))),
    );
    useCharges([]);
    setup();
    await waitFor(() =>
      expect(screen.getByText(/Pricing snapshot not available/i)).toBeInTheDocument(),
    );
  });
});

// GAP-077 — per-component (deposit/balance) owner-money split of the schedule.
const netToOwnerBlock = {
  currency_code: "GBP",
  gross_total: "2500.00",
  commission: "500.00",
  tax: "325.00",
  net_to_owner: "1675.00",
};

const depositSplit = {
  purpose: "deposit",
  status: "succeeded",
  due_at: "2026-05-15T12:00:00Z",
  gross: "750.00",
  commission: "150.00",
  tax: "97.50",
  net_to_owner: "502.50",
};

const balanceSplit = {
  purpose: "balance",
  status: "pending",
  due_at: "2026-06-01T12:00:00Z",
  gross: "1750.00",
  commission: "350.00",
  tax: "227.50",
  net_to_owner: "1172.50",
};

function useBooking(overrides: Record<string, unknown>) {
  server.use(
    http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
      HttpResponse.json(bookingFixture({}, overrides)),
    ),
  );
}

describe("FinanceTab — payment schedule split", () => {
  it("renders one row per component plus a totals row, all money formatted", async () => {
    useBooking({ payment_splits: [depositSplit, balanceSplit], net_to_owner: netToOwnerBlock });
    useCharges([]);
    setup();

    const heading = await screen.findByText("Payment schedule split");
    const section = within(heading.closest("section")!);

    // Purpose labels + per-row due dates.
    expect(section.getByText("Deposit")).toBeInTheDocument();
    expect(section.getByText("Balance")).toBeInTheDocument();
    expect(section.getByText("Due 15 May 2026")).toBeInTheDocument();
    expect(section.getByText("Due 1 Jun 2026")).toBeInTheDocument();

    // Commission figures appear only under an explicit "Commission" header.
    expect(section.getByText("Commission")).toBeInTheDocument();

    // Row cells.
    const depositRow = section.getByText("Deposit").closest("tr")!;
    expect(depositRow.textContent).toContain("£750.00");
    expect(depositRow.textContent).toContain("£150.00");
    expect(depositRow.textContent).toContain("£97.50");
    expect(depositRow.textContent).toContain("£502.50");
    const balanceRow = section.getByText("Balance").closest("tr")!;
    expect(balanceRow.textContent).toContain("£1,750.00");
    expect(balanceRow.textContent).toContain("£1,172.50");

    // Totals row sums the decimal strings exactly.
    const totalsRow = section.getByText("Totals").closest("tr")!;
    expect(totalsRow.textContent).toContain("£2,500.00");
    expect(totalsRow.textContent).toContain("£500.00");
    expect(totalsRow.textContent).toContain("£325.00");
    expect(totalsRow.textContent).toContain("£1,675.00");

    // Splits sum to the booking net — no drift caveat.
    expect(
      screen.queryByText(/schedule does not currently sum to the booking total/i),
    ).not.toBeInTheDocument();
  });

  it("is absent when payment_splits is an empty array", async () => {
    useBooking({ payment_splits: [], net_to_owner: netToOwnerBlock });
    useCharges([]);
    setup();

    await screen.findByRole("heading", { name: "Finance" });
    expect(screen.queryByText("Payment schedule split")).not.toBeInTheDocument();
  });

  it("is absent when payment_splits is null or missing", async () => {
    useBooking({ payment_splits: null });
    useCharges([]);
    setup();

    await screen.findByRole("heading", { name: "Finance" });
    expect(screen.queryByText("Payment schedule split")).not.toBeInTheDocument();
  });

  it("shows the drift caveat when split nets do not sum to the booking net", async () => {
    // Only the deposit component exists — Σ net (502.50) ≠ block net (1675.00).
    useBooking({ payment_splits: [depositSplit], net_to_owner: netToOwnerBlock });
    useCharges([]);
    setup();

    await screen.findByText("Payment schedule split");
    expect(
      screen.getByText(/schedule does not currently sum to the booking total/i),
    ).toBeInTheDocument();
  });

  it("badges a waived component", async () => {
    useBooking({
      payment_splits: [depositSplit, { ...balanceSplit, status: "waived" }],
      net_to_owner: netToOwnerBlock,
    });
    useCharges([]);
    setup();

    await screen.findByText("Payment schedule split");
    const balanceRow = screen.getByText("Balance").closest("tr")!;
    expect(within(balanceRow as HTMLElement).getByText("Waived")).toBeInTheDocument();
    const depositRow = screen.getByText("Deposit").closest("tr")!;
    expect(depositRow.textContent).not.toMatch(/waived/i);
  });
});

describe("FinanceTab — manual charges", () => {
  it("renders charge rows with signed amounts and the charges total", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json(
          bookingFixture({ total: "100.00" }, { charges_total: "-350.00", total: "1150.00" }),
        ),
      ),
    );
    useCharges([
      chargeItem({ id: 1, label: "Late checkout", amount: "150.00" }),
      chargeItem({ id: 2, label: "Goodwill credit", amount: "-500.00" }),
    ]);
    setup();

    expect(await screen.findByText("Late checkout")).toBeInTheDocument();
    expect(screen.getByText("Goodwill credit")).toBeInTheDocument();
    expect(screen.getByText(/£-500\.00/)).toBeInTheDocument();
    expect(screen.getByText("Charges total")).toBeInTheDocument();
    expect(screen.getByText(/£-350\.00/)).toBeInTheDocument();
    // Guest-facing total including charges, from the API `total` (also shown
    // on the layout rail, hence getAllByText).
    expect(screen.getAllByText(/£1,150\.00/).length).toBeGreaterThan(0);
  });

  it("marks non-commissionable charges and leaves default rows unmarked", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
    );
    useCharges([
      chargeItem({ id: 1, label: "Late checkout", amount: "150.00" }),
      chargeItem({ id: 2, label: "Chef pass-through", amount: "300.00", commissionable: false }),
    ]);
    setup();

    expect(await screen.findByText("Chef pass-through")).toBeInTheDocument();
    expect(screen.getAllByText(/non-commissionable/i)).toHaveLength(1);
    const flaggedRow = screen.getByText("Chef pass-through").closest("tr");
    expect(flaggedRow).not.toBeNull();
    expect(flaggedRow!.textContent).toMatch(/non-commissionable/i);
    const defaultRow = screen.getByText("Late checkout").closest("tr");
    expect(defaultRow!.textContent).not.toMatch(/non-commissionable/i);
  });

  it("renders and operates without a pricing snapshot (legacy bookings)", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
    );
    useCharges([chargeItem()]);
    setup();

    // Snapshot section degrades to its empty state…
    expect(await screen.findByText(/Pricing snapshot not available/i)).toBeInTheDocument();
    // …but the charges UI is fully present.
    expect(screen.getByText("Manual charges")).toBeInTheDocument();
    expect(await screen.findByText("Late checkout")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add charge/i })).toBeEnabled();
  });

  it("disables Add charge with a tooltip when the user lacks the role", async () => {
    clearRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
    );
    useCharges([]);
    setup();

    const addBtn = await screen.findByRole("button", { name: /add charge/i });
    expect(addBtn).toBeDisabled();
  });

  it("opens the create dialog from the Add charge button", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
    );
    useCharges([]);
    setup();

    await screen.findByText(/no manual charges/i);
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("deletes a charge after confirmation", async () => {
    let deleted = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture({}))),
      http.delete(`/api/v1/bookings/${BOOKING_ID}/charge-items/1`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    useCharges([chargeItem({ id: 1 })]);
    setup();

    await screen.findByText("Late checkout");
    await userEvent.click(screen.getByRole("button", { name: /delete late checkout/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^delete charge$/i }));
    await waitFor(() => expect(deleted).toBe(true));
  });
});
