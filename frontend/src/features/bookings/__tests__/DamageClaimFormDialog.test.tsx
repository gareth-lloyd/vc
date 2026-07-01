import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { DamageClaimFormDialog } from "../components/DamageClaimFormDialog";
import type { DamageClaim } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeClaim(overrides: Partial<DamageClaim> = {}): DamageClaim {
  return {
    id: 7,
    reference: "DC-000007",
    booking: BOOKING_ID,
    amount: "500.00",
    description: "Broken window",
    status: "open",
    currency: 1,
    currency_code: "GBP",
    itemized_lines: [],
    photos: [],
    accepted_by_guest_at: null,
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

describe("DamageClaimFormDialog (create)", () => {
  function setupCreate() {
    return renderWithProviders(
      <DamageClaimFormDialog
        mode="create"
        bookingId={BOOKING_ID}
        currencyCode="GBP"
        open
        onOpenChange={() => {}}
      />,
    );
  }

  it("POSTs description + amount + itemised lines and closes on success", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeClaim({ id: 100 }), { status: 201 });
      }),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/description/i), "Broken window");
    await userEvent.type(screen.getByLabelText("Amount"), "500.00");
    await userEvent.click(screen.getByRole("button", { name: /add line/i }));
    await userEvent.type(screen.getByLabelText(/line 1 description/i), "Glazing");
    await userEvent.type(screen.getByLabelText(/line 1 amount/i), "500.00");
    await userEvent.click(screen.getByRole("button", { name: /file claim/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({
      description: "Broken window",
      amount: "500.00",
      itemized_lines: [{ label: "Glazing", amount: "500.00" }],
    });
  });

  it("shows the booking currency as static text", () => {
    setupCreate();
    expect(screen.getByText("GBP")).toBeInTheDocument();
  });

  it("rejects a zero amount inline before submitting", async () => {
    setupCreate();
    await userEvent.type(screen.getByLabelText(/description/i), "Nothing");
    await userEvent.type(screen.getByLabelText("Amount"), "0.00");
    await userEvent.click(screen.getByRole("button", { name: /file claim/i }));

    expect(await screen.findByText(/greater than zero/i)).toBeInTheDocument();
  });

  it("maps a 400 field error inline and stays open", async () => {
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { amount: ["Amount must be greater than zero."] },
          },
          { status: 400 },
        ),
      ),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/description/i), "Claim");
    await userEvent.type(screen.getByLabelText("Amount"), "1.00");
    await userEvent.click(screen.getByRole("button", { name: /file claim/i }));

    expect(await screen.findByText(/greater than zero/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("toasts on a 500 and stays open", async () => {
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    setupCreate();

    await userEvent.type(screen.getByLabelText(/description/i), "Claim");
    await userEvent.type(screen.getByLabelText("Amount"), "500.00");
    await userEvent.click(screen.getByRole("button", { name: /file claim/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("DamageClaimFormDialog (edit)", () => {
  it("PATCHes the claim with the edited fields", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/damage-claims/7`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeClaim({ amount: "650.00" }));
      }),
    );
    renderWithProviders(
      <DamageClaimFormDialog
        mode="edit"
        bookingId={BOOKING_ID}
        currencyCode="GBP"
        claim={makeClaim()}
        open
        onOpenChange={() => {}}
      />,
    );

    const amount = screen.getByLabelText("Amount");
    await userEvent.clear(amount);
    await userEvent.type(amount, "650.00");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toMatchObject({ description: "Broken window", amount: "650.00" });
  });
});
