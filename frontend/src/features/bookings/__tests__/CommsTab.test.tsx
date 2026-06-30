import { http, HttpResponse } from "msw";
import { Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { CommsTab } from "../tabs/CommsTab";
import type { BookingDetail } from "../schemas";
import type { UserMe } from "@/features/auth/schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

const booking: BookingDetail = {
  id: BOOKING_ID,
  reference: "B-AAA-001",
  status: "awaiting_deposit",
  property: 12,
  agent: null,
  assigned_to: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 4,
  children: 2,
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

const sampleEmail = {
  id: 7,
  template_key: "booking.deposit_request",
  template_version: 1,
  to: ["guest@example.com"],
  cc: [],
  bcc: [],
  from_email: "noreply@example.com",
  subject: "Deposit for B-AAA-001",
  status: "sent",
  queued_at: "2026-05-10T09:00:00Z",
  sent_at: "2026-05-10T09:00:05Z",
  failure_reason: "",
  sender_user_id: null,
  smtp_profile_id: 1,
  provider_reference: "",
  correlation: { booking_id: BOOKING_ID },
};

function asReservationsUser() {
  const me: UserMe = {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
  };
  useAuthStore.getState().setMe(me, {
    role: "RESERVATIONS",
    is_superuser: false,
    permissions: [],
  });
}

function asViewer() {
  const me: UserMe = {
    id: 2,
    email: "v@v.com",
    first_name: "V",
    last_name: "Iewer",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
  };
  useAuthStore.getState().setMe(me, { role: "VIEWER", is_superuser: false, permissions: [] });
}

afterEach(() => {
  server.resetHandlers();
  useAuthStore.getState().clear();
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
});

function setup() {
  // CommsTab reads `booking` from outlet context — mount it under a
  // mock layout so the context shape matches BookingDetailLayout.
  function Layout() {
    return <Outlet context={{ booking }} />;
  }
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<Layout />}>
        <Route path="comms" element={<CommsTab />} />
      </Route>
    </Routes>,
    { route: `/bookings/${BOOKING_ID}/comms` },
  );
}

describe("CommsTab", () => {
  beforeEach(() => {
    asReservationsUser();
  });

  it("lists emails with subject, recipient and status", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () =>
        HttpResponse.json({ count: 1, next: null, previous: null, results: [sampleEmail] }),
      ),
    );
    setup();
    expect(await screen.findByText("Deposit for B-AAA-001")).toBeInTheDocument();
    expect(screen.getByText(/guest@example\.com/)).toBeInTheDocument();
    // Localized status label "Sent" appears in the badge.
    expect(screen.getByText(/^Sent$/)).toBeInTheDocument();
  });

  it("renders the empty state when the list is empty", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    expect(await screen.findByText(/no emails yet/i)).toBeInTheDocument();
  });

  it("renders the error state with retry on a server error", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    setup();
    expect(await screen.findByText(/couldn't load emails/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("posts to :resend on confirm and refreshes the list", async () => {
    let resendCalled = false;
    let refetchCount = 0;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () => {
        refetchCount += 1;
        return HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [sampleEmail],
        });
      }),
      http.post(`/api/v1/bookings/${BOOKING_ID}/emails/7:resend`, async ({ request }) => {
        resendCalled = true;
        const body = (await request.json()) as { idempotency_key?: string };
        expect(typeof body.idempotency_key).toBe("string");
        return HttpResponse.json({ ...sampleEmail, id: 8, status: "queued" }, { status: 201 });
      }),
    );

    setup();
    await userEvent.click(await screen.findByRole("button", { name: /^resend$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^resend$/i }));
    await waitFor(() => expect(resendCalled).toBe(true));
    await waitFor(() => expect(refetchCount).toBeGreaterThanOrEqual(2));
    expect(toast.success).toHaveBeenCalled();
  });

  it("renders the em-dash placeholder when an email has an empty subject", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [{ ...sampleEmail, id: 12, subject: "" }],
        }),
      ),
    );
    setup();
    const subject = await screen.findByText("—");
    expect(subject).toBeInTheDocument();
  });

  it("disables the resend button for viewers", async () => {
    asViewer();
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/emails`, () =>
        HttpResponse.json({ count: 1, next: null, previous: null, results: [sampleEmail] }),
      ),
    );
    setup();
    expect(await screen.findByRole("button", { name: /^resend$/i })).toBeDisabled();
  });
});
