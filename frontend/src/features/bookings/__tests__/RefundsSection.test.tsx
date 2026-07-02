import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
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
  useAuthStore.setState({ user: null, role: null, isSuperuser: false });
});

function setCurrentUserId(id: number) {
  useAuthStore.setState({
    user: {
      id,
      email: "op@example.com",
      first_name: "Op",
      last_name: "Erator",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      role: "accounts",
      preferred_language: "en",
    },
    role: "accounts",
    isSuperuser: false,
    status: "authenticated",
    pendingTfa: null,
  });
}

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

describe("RefundsSection (lifecycle actions)", () => {
  it("disables Approve when the current user requested the refund", async () => {
    setCurrentUserId(9); // matches makeRefund().requested_by
    server.use(listHandler([makeRefund({ status: "pending", requested_by: 9 })]));
    setup();

    const approve = await screen.findByRole("button", { name: /approve refund RF-000004/i });
    expect(approve).toBeDisabled();
  });

  it("approves a pending refund through the confirm dialog", async () => {
    setCurrentUserId(2); // a different approver
    let approved = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json([makeRefund({ status: approved ? "approved" : "pending" })]),
      ),
      http.post(`/api/v1/refunds/4:approve`, () => {
        approved = true;
        return HttpResponse.json(makeRefund({ status: "approved" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /approve refund RF-000004/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Refund approved"));
    expect(approved).toBe(true);
  });

  it("cancels a pending refund", async () => {
    setCurrentUserId(2);
    let cancelled = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json([makeRefund({ status: cancelled ? "cancelled" : "pending" })]),
      ),
      http.post(`/api/v1/refunds/4:cancel`, () => {
        cancelled = true;
        return HttpResponse.json(makeRefund({ status: "cancelled" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /cancel refund RF-000004/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel refund" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Refund cancelled"));
    expect(cancelled).toBe(true);
  });

  it("executes an approved refund through the step-up dialog, posting { tfa_code }", async () => {
    setCurrentUserId(2);
    let executed = false;
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json([makeRefund({ status: executed ? "executing" : "approved" })]),
      ),
      // Online gateway execution settles to `executing`, not `succeeded`.
      http.post(`/api/v1/refunds/4:execute`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        executed = true;
        return HttpResponse.json(makeRefund({ status: "executing" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /execute refund RF-000004/i }));
    // The step-up dialog demands a fresh authenticator code.
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/6-digit code/i), "123456");
    await userEvent.click(within(dialog).getByRole("button", { name: "Execute refund" }));

    await waitFor(() => expect(body).toEqual({ tfa_code: "123456" }));
    expect(toast.success).toHaveBeenCalledWith("Refund execution started");
    expect(await screen.findByText("Executing — awaiting settlement")).toBeInTheDocument();
  });

  it("keeps the step-up dialog open with the reason on an invalid code", async () => {
    setCurrentUserId(2);
    server.use(
      listHandler([makeRefund({ status: "approved" })]),
      http.post(`/api/v1/refunds/4:execute`, () =>
        HttpResponse.json(
          {
            code: "invalid_tfa_code",
            detail: "That code is invalid or already used.",
            field_errors: {},
          },
          { status: 400 },
        ),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /execute refund RF-000004/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/6-digit code/i), "000000");
    await userEvent.click(within(dialog).getByRole("button", { name: "Execute refund" }));

    expect(await screen.findByText(/invalid or already used/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("rejects a refund, posting { reason }", async () => {
    setCurrentUserId(2);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/refunds`, () =>
        HttpResponse.json([makeRefund({ status: body ? "rejected" : "pending" })]),
      ),
      http.post(`/api/v1/refunds/4:reject`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeRefund({ status: "rejected" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /reject refund RF-000004/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Duplicate of RF-000003");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject refund" }));

    await waitFor(() => expect(body).toEqual({ reason: "Duplicate of RF-000003" }));
    expect(toast.success).toHaveBeenCalledWith("Refund rejected");
  });

  it("surfaces the backend 409 detail inline in the step-up dialog", async () => {
    setCurrentUserId(2);
    server.use(
      listHandler([makeRefund({ status: "approved" })]),
      http.post(`/api/v1/refunds/4:execute`, () =>
        HttpResponse.json({ detail: "Refund is not in an executable state." }, { status: 409 }),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /execute refund RF-000004/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/6-digit code/i), "123456");
    await userEvent.click(within(dialog).getByRole("button", { name: "Execute refund" }));

    expect(await screen.findByText(/not in an executable state/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows no row actions for a terminal refund", async () => {
    server.use(listHandler([makeRefund({ status: "succeeded" })]));
    setup();

    await screen.findByText("RF-000004");
    expect(screen.queryByRole("button", { name: /approve refund/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /execute refund/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel refund/i })).not.toBeInTheDocument();
  });
});
