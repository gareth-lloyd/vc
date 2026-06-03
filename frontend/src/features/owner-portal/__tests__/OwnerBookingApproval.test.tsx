import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    status: "pending_owner_approval",
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
    can_approve: true,
    ...overrides,
  };
}

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

describe("Owner booking approval actions", () => {
  it("shows Approve/Decline when pending and can_approve", async () => {
    mockBooking();
    renderPage();
    expect(await screen.findByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /decline/i })).toBeInTheDocument();
  });

  it("hides the actions when can_approve is false", async () => {
    mockBooking({ can_approve: false });
    renderPage();
    await screen.findAllByText("VC-0007");
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  it("hides the actions when the booking is not pending", async () => {
    mockBooking({ status: "deposit_paid" });
    renderPage();
    await screen.findAllByText("VC-0007");
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  it("approves the booking", async () => {
    let approved = false;
    mockBooking();
    server.use(
      http.post("/api/v1/owner/bookings/7:approve", () => {
        approved = true;
        return HttpResponse.json(booking({ status: "awaiting_deposit", can_approve: false }));
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approved).toBe(true));
  });

  it("requires a reason before declining", async () => {
    mockBooking();
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /decline/i }));
    // Submit the dialog with an empty reason.
    await userEvent.click(screen.getByRole("button", { name: /decline booking/i }));
    expect(await screen.findByText(/please give a reason/i)).toBeInTheDocument();
  });

  it("posts the decline reason", async () => {
    let body: unknown = null;
    mockBooking();
    server.use(
      http.post("/api/v1/owner/bookings/7:decline", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(booking({ status: "declined", can_approve: false }));
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^decline$/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Villa unavailable");
    await userEvent.click(screen.getByRole("button", { name: /decline booking/i }));

    await waitFor(() => expect(body).toEqual({ reason: "Villa unavailable" }));
  });
});
