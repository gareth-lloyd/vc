import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { ConciergeTab } from "../tabs/ConciergeTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 88;

const bookingFixture = {
  id: BOOKING_ID,
  reference: "B-CON-001",
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
  balance_due: "0.00",
  balance_due_at: null,
  site_source: "main_website",
  is_archived: false,
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  property_name: "Casa Norte",
  guest_name: "Ada Lovelace",
  guest_email: "ada@example.com",
  currency_code: "GBP",
  total: "2000.00",
  night_count: 7,
  pricing_snapshot: {},
  discount: "0.00",
  adjustment: "0.00",
};

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    booking: BOOKING_ID,
    tier: "quintessential",
    name: "Airport transfer",
    description: "Black car from MAD",
    quantity: 2,
    unit: "stay",
    unit_price: "125.00",
    currency: 1,
    status: "requested",
    notes: "",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function listResponse(items: ReturnType<typeof item>[]) {
  return { count: items.length, next: null, previous: null, results: items };
}

function setup(route = `/bookings/${BOOKING_ID}/concierge`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="concierge" replace />} />
        <Route path="concierge" element={<ConciergeTab />} />
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
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  server.use(http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture)));
});

afterEach(() => {
  server.resetHandlers();
  clearRole();
});

describe("ConciergeTab", () => {
  it("renders rows from the API", async () => {
    grantWriterRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/concierge-items`, () =>
        HttpResponse.json(listResponse([item({ id: 1, name: "Airport transfer" })])),
      ),
    );
    setup();
    expect(await screen.findByText("Airport transfer")).toBeInTheDocument();
    // 2 × £125.00 = £250.00
    expect(screen.getByText(/£250\.00/)).toBeInTheDocument();
  });

  it("disables Add service when the user lacks the role", async () => {
    clearRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/concierge-items`, () =>
        HttpResponse.json(listResponse([])),
      ),
    );
    setup();
    const addBtn = await screen.findByRole("button", { name: /add service/i });
    expect(addBtn).toBeDisabled();
  });

  it("opens the create dialog", async () => {
    grantWriterRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/concierge-items`, () =>
        HttpResponse.json(listResponse([])),
      ),
    );
    setup();
    await screen.findByText(/no concierge services yet/i);
    await userEvent.click(screen.getByRole("button", { name: /add service/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /add concierge service/i })).toBeInTheDocument();
  });

  it("confirms an item via the action menu", async () => {
    grantWriterRole();
    const stored = [item({ id: 5, name: "Yacht charter", status: "requested" })];
    let confirmCalls = 0;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/concierge-items`, () =>
        HttpResponse.json(listResponse(stored)),
      ),
      http.post(`/api/v1/bookings/${BOOKING_ID}/concierge-items/5:confirm`, () => {
        confirmCalls += 1;
        const updated = { ...stored[0], status: "confirmed" };
        stored[0] = updated;
        return HttpResponse.json(updated);
      }),
    );
    setup();
    await screen.findByText("Yacht charter");
    await userEvent.click(screen.getByRole("button", { name: /actions for yacht charter/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /confirm/i }));
    await waitFor(() => expect(confirmCalls).toBe(1));
    expect(toast.success).toHaveBeenCalled();
  });

  it("deletes an item via the confirm dialog", async () => {
    grantWriterRole();
    const stored = [item({ id: 9, name: "Spa booking" })];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/concierge-items`, () =>
        HttpResponse.json(listResponse(stored)),
      ),
      http.delete(`/api/v1/bookings/${BOOKING_ID}/concierge-items/9`, () => {
        stored.length = 0;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup();
    await screen.findByText("Spa booking");
    await userEvent.click(screen.getByRole("button", { name: /actions for spa booking/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /delete/i }));
    await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
    await waitFor(() => expect(screen.queryByText("Spa booking")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalled();
  });
});
