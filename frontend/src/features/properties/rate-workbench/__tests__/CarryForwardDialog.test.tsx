import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { CarryForwardDialog } from "../components/CarryForwardDialog";

const CARRY_URL = "/api/v1/properties/7/rate-plans:carry-forward";

function carriedPlan(overrides: Record<string, unknown> = {}) {
  return {
    id: 88,
    property: 7,
    name: "Carried forward 2027",
    currency: 5,
    currency_code: "GBP",
    periods: [],
    ...overrides,
  };
}

describe("CarryForwardDialog", () => {
  it("posts the currency code, target year and uplift", async () => {
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post(CARRY_URL, async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(carriedPlan(), { status: 201 });
      }),
    );
    const onCarried = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <CarryForwardDialog
        propertyId={7}
        currencyCode="GBP"
        targetYear={2027}
        open
        onOpenChange={() => {}}
        onCarried={onCarried}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/uplift/i), "5");
    await user.click(within(dialog).getByRole("button", { name: /carry/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ currency: "GBP", target_year: 2027, uplift_pct: 5 });
    await waitFor(() =>
      expect(onCarried).toHaveBeenCalledWith(expect.objectContaining({ id: 88 })),
    );
  });

  it("defaults the uplift to 0 when untouched", async () => {
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post(CARRY_URL, async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(carriedPlan(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <CarryForwardDialog
        propertyId={7}
        currencyCode="GBP"
        targetYear={2027}
        open
        onOpenChange={() => {}}
        onCarried={() => {}}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    // The field is pre-filled with the 0 default (not left blank) — guards
    // `defaultValues`, so the posted 0 can't silently come from a blank coerce.
    expect(within(dialog).getByLabelText(/uplift/i)).toHaveValue(0);
    await user.click(within(dialog).getByRole("button", { name: /carry/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ uplift_pct: 0 });
  });

  it("shows an inline 'nothing to carry' message on a 409 no_rate_available", async () => {
    server.use(
      http.post(CARRY_URL, () =>
        HttpResponse.json(
          { code: "no_rate_available", detail: "No prior rates to carry." },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <CarryForwardDialog
        propertyId={7}
        currencyCode="GBP"
        targetYear={2027}
        open
        onOpenChange={() => {}}
        onCarried={() => {}}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /carry/i }));

    expect(
      await within(dialog).findByText(
        "There are no earlier rates to carry forward for this property.",
      ),
    ).toBeInTheDocument();
    // Dialog stays open, no toast on a handled domain error.
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx instead of an inline field error", async () => {
    server.use(http.post(CARRY_URL, () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const user = userEvent.setup();
    renderWithProviders(
      <CarryForwardDialog
        propertyId={7}
        currencyCode="GBP"
        targetYear={2027}
        open
        onOpenChange={() => {}}
        onCarried={() => {}}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /carry/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(within(dialog).queryByText(/no earlier rates/i)).not.toBeInTheDocument();
  });
});
