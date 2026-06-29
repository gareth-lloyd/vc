import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ModifyDatesDialog } from "../components/ModifyDatesDialog";
import type { BookingDetail } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeBookingDetail(overrides: Partial<BookingDetail> = {}): BookingDetail {
  return {
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

describe("ModifyDatesDialog", () => {
  it("submits the new dates and toasts success", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-dates`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(
          makeBookingDetail({ date_from: "2026-07-10", date_to: "2026-07-17" }),
        );
      }),
    );

    const onOpenChange = vi.fn();
    renderWithProviders(
      <ModifyDatesDialog booking={makeBookingDetail()} open={true} onOpenChange={onOpenChange} />,
    );

    const dialog = screen.getByRole("dialog");
    const dateFrom = within(dialog).getByLabelText(/check-in/i) as HTMLInputElement;
    const dateTo = within(dialog).getByLabelText(/check-out/i) as HTMLInputElement;

    expect(dateFrom.value).toBe("2026-07-01");
    expect(dateTo.value).toBe("2026-07-08");

    await user.clear(dateFrom);
    await user.type(dateFrom, "2026-07-10");
    await user.clear(dateTo);
    await user.type(dateTo, "2026-07-17");

    await user.click(within(dialog).getByRole("button", { name: /save dates/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toEqual({ date_from: "2026-07-10", date_to: "2026-07-17" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("blocks client-side when date_to is before date_from", async () => {
    const user = userEvent.setup();
    const networkCalls = vi.fn();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-dates`, () => {
        networkCalls();
        return HttpResponse.json(makeBookingDetail());
      }),
    );

    renderWithProviders(
      <ModifyDatesDialog booking={makeBookingDetail()} open={true} onOpenChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog");
    const dateTo = within(dialog).getByLabelText(/check-out/i) as HTMLInputElement;
    await user.clear(dateTo);
    await user.type(dateTo, "2026-06-15");
    await user.click(within(dialog).getByRole("button", { name: /save dates/i }));

    expect(await within(dialog).findByText(/check-out must be after/i)).toBeInTheDocument();
    expect(networkCalls).not.toHaveBeenCalled();
  });

  it("surfaces a 400 field_errors.date_from inline and does NOT toast", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-dates`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { date_from: ["Conflicts with another booking"] },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <ModifyDatesDialog booking={makeBookingDetail()} open={true} onOpenChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /save dates/i }));

    expect(await within(dialog).findByText(/conflicts with another booking/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on 500 and leaves the dialog open", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-dates`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(
      <ModifyDatesDialog booking={makeBookingDetail()} open={true} onOpenChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /save dates/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
