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
import { DiscountFormDialog } from "../components/DiscountFormDialog";
import type { Discount } from "@/features/properties/schemas";

const existingDiscount: Discount = {
  id: 31,
  property: 7,
  name: "Repeat guests",
  code: null,
  rule_kind: "repeat_guest",
  kind: "percent",
  amount: "5.00",
  min_nights: 0,
  threshold_days: null,
  valid_from: "2026-01-01",
  valid_to: "2026-12-31",
  max_uses: null,
  uses_count: 0,
  is_active: true,
};

function renderCreate() {
  return renderWithProviders(
    <DiscountFormDialog
      propertyId={7}
      open
      onOpenChange={() => {}}
      mode="create"
      currencyCode="EUR"
    />,
  );
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>, dialog: HTMLElement) {
  await user.type(within(dialog).getByLabelText("Name"), "Early bird 10%");
  await user.type(within(dialog).getByLabelText("Amount"), "10");
  await user.type(within(dialog).getByLabelText("Valid from"), "2026-01-01");
  await user.type(within(dialog).getByLabelText("Valid to"), "2026-12-31");
}

describe("DiscountFormDialog create contract", () => {
  it("POSTs the exact wire payload — nulls included, no property key", async () => {
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/discounts", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ ...existingDiscount, id: 32, name: "Early bird 10%" });
      }),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    await fillRequired(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    // Full-body equality: a subset assert (toMatchObject) is exactly how the
    // min_nights:null regression slipped through before.
    expect(posted[0]).toEqual({
      name: "Early bird 10%",
      code: null,
      rule_kind: "promo_code",
      kind: "percent",
      amount: "10",
      min_nights: null,
      threshold_days: null,
      valid_from: "2026-01-01",
      valid_to: "2026-12-31",
      max_uses: null,
      is_active: true,
    });
    expect("property" in posted[0]).toBe(false);
  });

  it("shows a threshold-days input for early-bird kinds and posts its value", async () => {
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/discounts", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ ...existingDiscount, id: 33 });
      }),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    // promo_code (the default) has a Code input and no threshold input.
    expect(within(dialog).getByLabelText("Code")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Min days before arrival")).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox", { name: "Applies to" }));
    await user.click(await screen.findByRole("option", { name: "Early bird" }));

    // Early bird swaps the (meaningless) Code input for the threshold input,
    // labelled as a MINIMUM lead time (last minute would be a maximum).
    expect(within(dialog).queryByLabelText("Code")).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Min days before arrival"), "30");

    await fillRequired(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ rule_kind: "early_bird", threshold_days: 30, code: null });
  });

  it("requires a threshold for early-bird kinds and blocks submit inline", async () => {
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/discounts", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ ...existingDiscount, id: 34 });
      }),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("combobox", { name: "Applies to" }));
    await user.click(await screen.findByRole("option", { name: "Early bird" }));
    await fillRequired(user, dialog);
    // Threshold left blank: an early-bird discount without a lead-time floor
    // would apply to every booking — the schema must refuse it.
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(
      await within(dialog).findByText("Enter the days-before-arrival threshold."),
    ).toBeInTheDocument();
    expect(posted).toHaveLength(0);
  });

  it("toasts on a 5xx instead of surfacing field errors", async () => {
    server.use(
      http.post("/api/v1/properties/7/discounts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    await fillRequired(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it("maps a server field_errors.code onto the code field inline", async () => {
    server.use(
      http.post("/api/v1/properties/7/discounts", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { code: ["discount with this code already exists."] },
          },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    await fillRequired(user, dialog);
    await user.type(within(dialog).getByLabelText("Code"), "SUMMER");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(
      await within(dialog).findByText("discount with this code already exists."),
    ).toBeInTheDocument();
    // Dialog stays open for correction.
    expect(within(dialog).getByLabelText("Code")).toBeInTheDocument();
  });

  it("routes unmapped field errors into the top-level alert", async () => {
    server.use(
      http.post("/api/v1/properties/7/discounts", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { property: ["This field is required."] },
          },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderCreate();

    const dialog = await screen.findByRole("dialog");
    await fillRequired(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(
      await within(dialog).findByText(/Validation failed This field is required\./),
    ).toBeInTheDocument();
  });
});

describe("DiscountFormDialog edit mode", () => {
  it("preserves a stored promo code when the rule kind is switched away", async () => {
    const promoDiscount: Discount = {
      ...existingDiscount,
      id: 40,
      name: "Summer promo",
      code: "SUMMER10",
      rule_kind: "promo_code",
    };
    const patched: Array<Record<string, unknown>> = [];
    server.use(
      http.patch("/api/v1/discounts/40", async ({ request }) => {
        patched.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ ...promoDiscount, rule_kind: "length_of_stay" });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <DiscountFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="edit"
        entity={promoDiscount}
        currencyCode="EUR"
      />,
    );

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("combobox", { name: "Applies to" }));
    await user.click(await screen.findByRole("option", { name: "Length of stay" }));
    // The Code input is now hidden, but the live code customers hold must NOT
    // be wiped by an edit that merely changes the rule kind.
    expect(within(dialog).queryByLabelText("Code")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0]).toMatchObject({ rule_kind: "length_of_stay", code: "SUMMER10" });
  });

  it("shows a stored min_nights of 0 as an empty 'no minimum' input", async () => {
    renderWithProviders(
      <DiscountFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="edit"
        entity={existingDiscount}
        currencyCode="EUR"
      />,
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Min nights")).toHaveValue(null);
  });
});
