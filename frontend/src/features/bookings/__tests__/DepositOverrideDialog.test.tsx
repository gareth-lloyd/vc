import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { DepositOverrideDialog } from "../components/DepositOverrideDialog";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 91;

// A minimal-but-valid BookingDetail so `bookingDetailSchema.parse` succeeds on
// the mutation response.
function bookingDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: BOOKING_ID,
    reference: "B-OVR-001",
    status: "awaiting_deposit",
    property: 12,
    agent: null,
    assigned_to: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: 1,
    rental_price: "1400.00",
    balance_due: "1400.00",
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
    total: "1400.00",
    charges_total: "0.00",
    night_count: 7,
    pricing_snapshot: {},
    terms_version: 1,
    terms_accepted_at: "2026-05-01T00:00:00Z",
    payment_method: "card",
    cancel_reason: "",
    cancelled_at: null,
    deposit_override_amount: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("DepositOverrideDialog", () => {
  it("POSTs the amount + reason and closes on success", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:deposit-override`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(bookingDetail({ deposit_override_amount: "500.00" }));
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(
      <DepositOverrideDialog bookingId={BOOKING_ID} open onOpenChange={onOpenChange} />,
    );

    await userEvent.type(screen.getByLabelText(/deposit amount/i), "500.00");
    await userEvent.type(screen.getByLabelText(/reason/i), "Carry-over from B-0001");
    await userEvent.click(screen.getByRole("button", { name: /save override/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toEqual({ amount: "500.00", reason: "Carry-over from B-0001" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("pre-fills the current override when editing", () => {
    renderWithProviders(
      <DepositOverrideDialog
        bookingId={BOOKING_ID}
        open
        onOpenChange={() => {}}
        currentAmount="750.00"
      />,
    );
    expect(screen.getByLabelText(/deposit amount/i)).toHaveValue("750.00");
  });

  it("rejects a non-numeric amount inline without POSTing", async () => {
    let posted = false;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:deposit-override`, () => {
        posted = true;
        return HttpResponse.json(bookingDetail());
      }),
    );
    renderWithProviders(
      <DepositOverrideDialog bookingId={BOOKING_ID} open onOpenChange={() => {}} />,
    );

    await userEvent.type(screen.getByLabelText(/deposit amount/i), "abc");
    await userEvent.click(screen.getByRole("button", { name: /save override/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(posted).toBe(false);
  });
});
