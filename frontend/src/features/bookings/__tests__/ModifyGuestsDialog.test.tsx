import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ModifyGuestsDialog } from "../components/ModifyGuestsDialog";
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
    adults: 2,
    children: 1,
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

describe("ModifyGuestsDialog", () => {
  it("submits adults and children and toasts success", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-guests`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeBookingDetail({ adults: 3, children: 2 }));
      }),
    );

    const onOpenChange = vi.fn();
    renderWithProviders(
      <ModifyGuestsDialog booking={makeBookingDetail()} open={true} onOpenChange={onOpenChange} />,
    );

    const dialog = screen.getByRole("dialog");
    const adults = within(dialog).getByLabelText(/adults/i) as HTMLInputElement;
    const children = within(dialog).getByLabelText(/children/i) as HTMLInputElement;
    await user.clear(adults);
    await user.type(adults, "3");
    await user.clear(children);
    await user.type(children, "2");

    await user.click(within(dialog).getByRole("button", { name: /save guests/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toEqual({ adults: 3, children: 2 });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("blocks client-side when adults is 0", async () => {
    const user = userEvent.setup();
    const networkCalls = vi.fn();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-guests`, () => {
        networkCalls();
        return HttpResponse.json(makeBookingDetail());
      }),
    );

    renderWithProviders(
      <ModifyGuestsDialog booking={makeBookingDetail()} open={true} onOpenChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog");
    const adults = within(dialog).getByLabelText(/adults/i) as HTMLInputElement;
    await user.clear(adults);
    await user.type(adults, "0");
    await user.click(within(dialog).getByRole("button", { name: /save guests/i }));

    expect(await within(dialog).findByText(/at least one adult/i)).toBeInTheDocument();
    expect(networkCalls).not.toHaveBeenCalled();
  });

  it("surfaces a 400 field_errors.adults inline and does NOT toast", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:modify-guests`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { adults: ["Exceeds property capacity"] },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <ModifyGuestsDialog booking={makeBookingDetail()} open={true} onOpenChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /save guests/i }));

    expect(await within(dialog).findByText(/exceeds property capacity/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
