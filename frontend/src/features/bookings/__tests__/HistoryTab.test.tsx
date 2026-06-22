import { http, HttpResponse } from "msw";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { OverviewTab } from "../tabs/OverviewTab";
import { HistoryTab } from "../tabs/HistoryTab";
import type { BookingDetail } from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

const bookingFixture = {
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
  children: 1,
  currency: 1,
  rental_price: "1500.00",
  balance_due: "2500.00",
  balance_due_at: "2026-06-01",
  amount_paid: "1500.00",
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
  pricing_snapshot: {},
  discount: "0.00",
  adjustment: "0.00",
  terms_version: 1,
  terms_accepted_at: "2026-05-01T00:00:00Z",
  payment_method: "card",
  cancel_reason: "",
  cancelled_at: null,
  net_to_owner: {
    currency_code: "GBP",
    gross_total: "2500.00",
    commission: "500.00",
    tax: "0.00",
    net_to_owner: "2000.00",
  },
};

function asAdmin() {
  useAuthStore.setState({
    user: null,
    role: "ADMIN",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function asNonAdmin() {
  useAuthStore.setState({
    user: null,
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

afterEach(() => {
  server.resetHandlers();
  // Reset the module-global auth store so role state can't leak between tests.
  useAuthStore.getState().clear();
});

describe("booking HistoryTab", () => {
  it("queries the booking's audit trail by entity_type/entity_id", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/audit-log", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );

    const context: BookingOutletContext = { booking: { id: 51 } as BookingDetail };
    renderWithProviders(
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/x" element={<HistoryTab />} />
        </Route>
      </Routes>,
      { route: "/x" },
    );

    await waitFor(() => expect(capturedUrl).not.toBeNull());
    expect(capturedUrl!.searchParams.get("entity_type")).toBe("reservations.booking");
    expect(capturedUrl!.searchParams.get("entity_id")).toBe("51");
  });
});

describe("booking History tab nav gating", () => {
  beforeEach(() => {
    server.use(http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)));
  });

  function setup(route = "/bookings/51/overview") {
    return renderWithProviders(
      <Routes>
        <Route path="/bookings/:id" element={<BookingDetailLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewTab />} />
          <Route path="history" element={<HistoryTab />} />
        </Route>
      </Routes>,
      { route },
    );
  }

  it("shows the History tab to an admin", async () => {
    asAdmin();
    setup();
    await waitFor(() => expect(screen.getAllByText("B-AAA-001").length).toBeGreaterThan(0));
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });

  it("hides the History tab from a non-admin", async () => {
    asNonAdmin();
    setup();
    await waitFor(() => expect(screen.getAllByText("B-AAA-001").length).toBeGreaterThan(0));
    expect(screen.queryByRole("link", { name: "History" })).not.toBeInTheDocument();
  });
});
