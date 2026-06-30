import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { RefundsSection } from "../components/RefundsSection";
import type { Refund } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeRefund(overrides: Partial<Refund> = {}): Refund {
  return {
    id: 4,
    reference: "RF-000004",
    booking: BOOKING_ID,
    against_payment: null,
    purpose_track: "balance",
    amount: "250.00",
    currency: 1,
    status: "pending",
    reason_code: "overpayment",
    reason_notes: "Guest paid twice",
    method: "online_gateway",
    requested_by: 9,
    requested_at: "2026-06-01T00:00:00Z",
    approved_by: null,
    approved_at: null,
    rejected_by: null,
    rejected_at: null,
    rejection_reason: "",
    executed_by: null,
    executed_at: null,
    cancelled_at: null,
    settled_at: null,
    failure_reason: "",
    meta: {},
    security_deposit: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

// The booking refunds endpoint is a PLAIN ARRAY (not DRF-paginated).
function listHandler(rows: Refund[]) {
  return http.get(`/api/v1/bookings/${BOOKING_ID}/refunds`, () => HttpResponse.json(rows));
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

function setup(canWrite = true) {
  return renderWithProviders(
    <RefundsSection bookingId={BOOKING_ID} currency="GBP" canWrite={canWrite} />,
  );
}

describe("RefundsSection (list + create)", () => {
  it("renders refund rows with reference, amount, status and method", async () => {
    server.use(listHandler([makeRefund()]));
    setup();

    expect(await screen.findByText("RF-000004")).toBeInTheDocument();
    // Money is formatted with the booking currency (no currency_code on the wire).
    expect(screen.getByText("£250.00")).toBeInTheDocument();
    expect(screen.getByText("Pending approval")).toBeInTheDocument();
    expect(screen.getByText("Online gateway")).toBeInTheDocument();
  });

  it("shows an empty state when there are no refunds", async () => {
    server.use(listHandler([]));
    setup();

    expect(await screen.findByText(/no refunds/i)).toBeInTheDocument();
  });

  it("disables the request button without the accounts role", async () => {
    server.use(listHandler([]));
    setup(false);

    const requestButton = await screen.findByRole("button", { name: /request refund/i });
    expect(requestButton).toBeDisabled();
  });

  it("POSTs amount + taxonomy defaults and closes on success", async () => {
    let receivedBody: unknown = null;
    server.use(
      listHandler([]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/refunds`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeRefund({ id: 100 }), { status: 201 });
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /request refund/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Amount"), "250.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /request refund/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({
      amount: "250.00",
      purpose_track: "balance",
      reason_code: "other",
      method: "online_gateway",
    });
  });

  it("rejects a zero amount inline before submitting", async () => {
    server.use(listHandler([]));
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /request refund/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Amount"), "0.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /request refund/i }));

    expect(await within(dialog).findByText(/greater than zero/i)).toBeInTheDocument();
  });

  it("maps a 400 field error inline and stays open", async () => {
    server.use(
      listHandler([]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { amount: ["Amount exceeds the refundable total."] },
          },
          { status: 400 },
        ),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /request refund/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Amount"), "999.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /request refund/i }));

    expect(await screen.findByText(/exceeds the refundable total/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("toasts on a 500 and stays open", async () => {
    server.use(
      listHandler([]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /request refund/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Amount"), "250.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /request refund/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
