import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { PaymentsTab } from "../tabs/PaymentsTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 77;

const bookingFixture = {
  id: BOOKING_ID,
  reference: "B-PAY-001",
  status: "awaiting_balance",
  property: 12,
  guest: 99,
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
  currency_code: "GBP",
  total: "2000.00",
  night_count: 7,
  pricing_snapshot: {},
  discount: "0.00",
  adjustment: "0.00",
};

function track(overrides: Record<string, unknown> = {}) {
  return {
    booking: BOOKING_ID,
    purpose: "deposit",
    scheduled_amount: "500.00",
    paid_amount: "500.00",
    due_at: "2026-05-15T00:00:00Z",
    status: "succeeded",
    ...overrides,
  };
}

function setup(route = `/bookings/${BOOKING_ID}/payments`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="payments" replace />} />
        <Route path="payments" element={<PaymentsTab />} />
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
  server.use(
    http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture)),
    http.get(`/api/v1/bookings/${BOOKING_ID}/deposit`, () =>
      HttpResponse.json(track({ purpose: "deposit", status: "succeeded" })),
    ),
    http.get(`/api/v1/bookings/${BOOKING_ID}/balance`, () =>
      HttpResponse.json(
        track({
          purpose: "balance",
          scheduled_amount: "1500.00",
          paid_amount: "0.00",
          status: "pending",
          due_at: "2026-06-01T00:00:00Z",
        }),
      ),
    ),
    http.get(`/api/v1/bookings/${BOOKING_ID}/security`, () =>
      HttpResponse.json(
        track({
          purpose: "security_deposit",
          scheduled_amount: "300.00",
          paid_amount: "0.00",
          status: "pending",
          due_at: null,
        }),
      ),
    ),
    http.get(`/api/v1/bookings/${BOOKING_ID}/deposit/payments`, () => HttpResponse.json([])),
    http.get(`/api/v1/bookings/${BOOKING_ID}/balance/payments`, () => HttpResponse.json([])),
    http.get(`/api/v1/bookings/${BOOKING_ID}/security/payments`, () => HttpResponse.json([])),
  );
});

afterEach(() => {
  server.resetHandlers();
  clearRole();
});

describe("PaymentsTab", () => {
  it("renders all three tracks with money and status", async () => {
    grantWriterRole();
    setup();
    expect(await screen.findByText("Deposit")).toBeInTheDocument();
    expect(screen.getByText("Balance")).toBeInTheDocument();
    expect(screen.getByText("Security deposit")).toBeInTheDocument();
    // Balance: 0.00 of 1500.00
    await waitFor(() => expect(screen.getByText(/£0\.00 of £1,500\.00 paid/i)).toBeInTheDocument());
  });

  it("keys the track badge styling on the raw status while showing the label", async () => {
    grantWriterRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/security`, () =>
        HttpResponse.json(
          track({
            purpose: "security_deposit",
            scheduled_amount: "300.00",
            paid_amount: "0.00",
            status: "failed",
            due_at: null,
          }),
        ),
      ),
    );
    setup();
    // Deposit (succeeded) renders the humanised label with success styling.
    const depositSection = (await screen.findByText("Deposit")).closest("section")!;
    const paid = await within(depositSection).findByText("Paid");
    expect(paid.closest('[data-slot="badge"]')).toHaveClass("text-success");
    // Security (failed) renders its label with error styling — STATUS_TO_KIND
    // keys on the raw status, not the display text.
    const securitySection = screen.getByText("Security deposit").closest("section")!;
    const failed = await within(securitySection).findByText("Failed");
    expect(failed.closest('[data-slot="badge"]')).toHaveClass("text-danger");
  });

  it("disables actions when the user lacks the role", async () => {
    clearRole();
    setup();
    await screen.findByText("Deposit");
    const markReceived = screen.getAllByRole("button", { name: /mark received/i });
    expect(markReceived.length).toBeGreaterThan(0);
    for (const btn of markReceived) {
      expect(btn).toBeDisabled();
    }
  });

  it("disables the payment request when the scheduled amount is zero", async () => {
    // A £0.00 security deposit: there is nothing to request, so the button
    // must not offer to send a reminder for it.
    grantWriterRole();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/security`, () =>
        HttpResponse.json(
          track({
            purpose: "security_deposit",
            scheduled_amount: "0.00",
            paid_amount: "0.00",
            status: "pending",
            due_at: null,
          }),
        ),
      ),
    );
    setup();
    await screen.findByText("Security deposit");
    const securitySection = screen.getByText("Security deposit").closest("section")!;
    expect(within(securitySection).getByRole("button", { name: /send reminder/i })).toBeDisabled();
    // A non-zero pending track keeps its request button live.
    const balanceSection = screen.getByText("Balance").closest("section")!;
    expect(within(balanceSection).getByRole("button", { name: /send reminder/i })).toBeEnabled();
  });

  it("opens the mark-paid dialog when Mark received is clicked", async () => {
    grantWriterRole();
    setup();
    await screen.findByText("Balance");
    // Find the Mark received button inside the Balance track (second track).
    const buttons = screen.getAllByRole("button", { name: /mark received/i });
    // Deposit (succeeded) -> disabled. Balance/Security (pending) -> enabled.
    const enabled = buttons.filter((b) => !(b as HTMLButtonElement).disabled);
    expect(enabled.length).toBeGreaterThan(0);
    await userEvent.click(enabled[0]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /mark.*paid/i })).toBeInTheDocument();
  });
});
