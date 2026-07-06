import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { PropertyDefaultsPage } from "../PropertyDefaultsPage";
import type { PropertyDefaults } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function makeUser(overrides: Partial<UserMe> = {}): UserMe {
  return {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
    ...overrides,
  };
}

// GET fixture mirroring the backend model defaults: non-nullable columns with
// values, nullable currency, and note fields serialized as "" (never null).
function makeDefaults(overrides: Partial<PropertyDefaults> = {}): PropertyDefaults {
  return {
    availability_default: "available",
    bookings_require_pre_approval: false,
    requires_enquiry_first: false,
    currency: null,
    check_in_time: "16:30:00",
    check_out_time: "10:30:00",
    changeover_day: "any",
    min_nights_rental: 1,
    min_nights_rental_note: "",
    prices_entered_as: "gross",
    hold_duration_hours: 48,
    commission_calculation_type: "percent",
    commission_amount: "20.00",
    commission_note: "",
    tax_is_exempt: false,
    tax_percentage: "13.00",
    deposit_required: true,
    deposit_calculation_type: "percent",
    deposit_amount: "30.00",
    interim_required: false,
    interim_calculation_type: "percent",
    interim_amount: "0.00",
    days_interim_due_before_arrival: 0,
    days_balance_due_before_arrival: 60,
    security_deposit_required: true,
    security_deposit_calculation_type: "fixed",
    security_deposit_amount: "500.00",
    security_deposit_days_due_before_arrival: 14,
    security_deposit_days_refunded_after_departure: 7,
    security_deposit_payment_method: "card_hold",
    cancellation_fee_amount: "0.00",
    cancellation_fee_percent: "0.00",
    cancellation_window_days: 0,
    cancellation_notes: "",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const currenciesHandler = http.get("/api/v1/currencies", () =>
  HttpResponse.json(
    drfPage([
      { id: 1, code: "EUR", name: "Euro", symbol: "€", decimal_places: 2, is_active: true },
      { id: 2, code: "GBP", name: "Pound", symbol: "£", decimal_places: 2, is_active: true },
    ]),
  ),
);

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/property-defaults" element={<PropertyDefaultsPage />} />
    </Routes>,
    { route: "/admin/property-defaults" },
  );
}

beforeEach(() => {
  useAuthStore.getState().setMe(makeUser(), {
    role: "admin",
    is_superuser: false,
    permissions: [],
  });
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("PropertyDefaultsPage", () => {
  it("renders all five sections from the GET payload", async () => {
    server.use(
      currenciesHandler,
      http.get("/api/v1/property-defaults", () => HttpResponse.json(makeDefaults())),
    );
    renderPage();

    expect(await screen.findByRole("heading", { name: "Operational" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Commission & tax" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Payment schedule" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Security deposit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cancellation" })).toBeInTheDocument();

    // Spot-check one field per input kind: number, decimal string, select label.
    expect(screen.getByLabelText("Minimum nights")).toHaveValue(1);
    expect(screen.getByLabelText("Commission amount")).toHaveValue("20.00");
    expect(screen.getByLabelText("Balance due days before arrival")).toHaveValue(60);
    await waitFor(() =>
      expect(screen.getByLabelText("Payment method")).toHaveTextContent("Card hold"),
    );
  });

  it("PATCHes the full payload on save, keeping cleared notes as empty strings", async () => {
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      currenciesHandler,
      http.get("/api/v1/property-defaults", () => HttpResponse.json(makeDefaults())),
      http.patch("/api/v1/property-defaults", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          makeDefaults({ min_nights_rental: 3, updated_at: "2026-01-02T00:00:00Z" }),
        );
      }),
    );
    renderPage();

    const minNights = await screen.findByLabelText("Minimum nights");
    await userEvent.clear(minNights);
    await userEvent.type(minNights, "3");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    const body = patchBody as unknown as Record<string, unknown>;
    expect(body.min_nights_rental).toBe(3);
    // Note columns are non-nullable server-side: empty textareas must submit
    // "" — never null.
    expect(body.min_nights_rental_note).toBe("");
    expect(body.commission_note).toBe("");
    expect(body.cancellation_notes).toBe("");
    // Nullable FK stays null when unset.
    expect(body.currency).toBeNull();
    // Full-payload PATCH: untouched fields ride along unchanged.
    expect(body.deposit_amount).toBe("30.00");
    expect(body.security_deposit_payment_method).toBe("card_hold");
  });

  it("maps a 4xx field error onto the form inline alert", async () => {
    server.use(
      currenciesHandler,
      http.get("/api/v1/property-defaults", () => HttpResponse.json(makeDefaults())),
      http.patch("/api/v1/property-defaults", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: {
              min_nights_rental: ["Ensure this value is greater than or equal to 0."],
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderPage();

    const minNights = await screen.findByLabelText("Minimum nights");
    await userEvent.clear(minNights);
    await userEvent.type(minNights, "5");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ensure this value is greater than or equal to 0.",
    );
  });
});
