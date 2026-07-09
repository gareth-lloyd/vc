import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ChargeItemFormDialog } from "../components/ChargeItemFormDialog";
import type { BookingChargeItem } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeItem(overrides: Partial<BookingChargeItem> = {}): BookingChargeItem {
  return {
    id: 7,
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

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("ChargeItemFormDialog (create)", () => {
  function setupCreate() {
    return renderWithProviders(
      <ChargeItemFormDialog
        mode="create"
        bookingId={BOOKING_ID}
        currencyCode="GBP"
        open
        onOpenChange={() => {}}
      />,
    );
  }

  it("POSTs the body and closes on success", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/charge-items`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ id: 100 }), { status: 201 });
      }),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/label/i), "Late checkout");
    await userEvent.type(screen.getByLabelText(/amount/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({
      label: "Late checkout",
      amount: "150.00",
      commissionable: true,
    });
  });

  it("sends commissionable: false when the checkbox is unticked", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/charge-items`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ id: 101, commissionable: false }), { status: 201 });
      }),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/label/i), "Chef pass-through");
    await userEvent.type(screen.getByLabelText(/amount/i), "300.00");
    await userEvent.click(screen.getByRole("checkbox", { name: /commissionable/i }));
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({ commissionable: false });
  });

  it("shows the booking currency as static text", () => {
    setupCreate();
    expect(screen.getByText("GBP")).toBeInTheDocument();
  });

  it("rejects a zero amount inline before submitting", async () => {
    setupCreate();
    await userEvent.type(screen.getByLabelText(/label/i), "Nothing");
    await userEvent.type(screen.getByLabelText(/amount/i), "0.00");
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));

    expect(await screen.findByText(/must not be zero/i)).toBeInTheDocument();
  });

  it("maps a 400 field error inline and stays open", async () => {
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/charge-items`, () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { amount: ["This would make the booking total negative."] },
          },
          { status: 400 },
        ),
      ),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/label/i), "Too generous");
    await userEvent.type(screen.getByLabelText(/amount/i), "-9999.00");
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));

    expect(await screen.findByText(/total negative/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("toasts on a 500 and stays open", async () => {
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/charge-items`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/label/i), "Late checkout");
    await userEvent.type(screen.getByLabelText(/amount/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("ChargeItemFormDialog (edit)", () => {
  it("PATCHes the item with the edited fields", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/charge-items/7`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ amount: "-75.00" }));
      }),
    );
    renderWithProviders(
      <ChargeItemFormDialog
        mode="edit"
        bookingId={BOOKING_ID}
        currencyCode="GBP"
        item={makeItem()}
        open
        onOpenChange={() => {}}
      />,
    );

    const amount = screen.getByLabelText(/amount/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, "-75.00");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({ label: "Late checkout", amount: "-75.00" });
  });

  it("seeds the commissionable checkbox from the item", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/charge-items/7`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ commissionable: false }));
      }),
    );
    renderWithProviders(
      <ChargeItemFormDialog
        mode="edit"
        bookingId={BOOKING_ID}
        currencyCode="GBP"
        item={makeItem({ commissionable: false })}
        open
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByRole("checkbox", { name: /commissionable/i })).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({ commissionable: false });
  });
});
