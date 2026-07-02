import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { InspectorPanel } from "../components/InspectorPanel";

const service = {
  id: 9,
  property: 7,
  name: "Daily maid",
  copy: "Daily maid service",
  notes: null,
  sort_order: 0,
  is_active: true,
  applies_from: null,
  applies_to: null,
};
const extra = {
  id: 11,
  property: 7,
  name: "Airport transfer",
  kind: "other",
  calc: "fixed_per_stay",
  amount: "120",
  currency: 1,
  currency_code: "EUR",
  is_mandatory: false,
};
const discount = {
  id: 21,
  property: 7,
  name: "Early bird",
  code: "EARLY",
  rule_kind: "early_bird",
  kind: "percent",
  amount: "10",
  threshold_days: 60,
  valid_from: "2026-01-01",
  valid_to: "2026-03-01",
};
const eurCurrency = {
  id: 1,
  code: "EUR",
  name: "Euro",
  symbol: "€",
  decimal_places: 2,
  is_active: true,
};

function installReads() {
  server.use(
    http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([service]))),
    http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([extra]))),
    http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([discount]))),
    // The extra dialog seeds its currency default from settings and lists
    // currencies via CurrencyPicker.
    http.get("/api/v1/properties/7/settings", () =>
      HttpResponse.json({ property: 7, currency: 1, currency_code: "EUR" }),
    ),
    http.get("/api/v1/currencies", () => HttpResponse.json(drfPage([eurCurrency]))),
  );
}

function renderPanel(canWrite = true) {
  return renderWithProviders(
    <InspectorPanel propertyId={7} canWrite={canWrite} currencyCode="EUR" defaultCurrencyId={1} />,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("InspectorPanel", () => {
  it("renders the three sections with their items", async () => {
    installReads();
    renderPanel();
    expect(await screen.findByText("Daily maid")).toBeInTheDocument();
    expect(screen.getByText("Airport transfer")).toBeInTheDocument();
    expect(screen.getByText("Early bird")).toBeInTheDocument();
  });

  it("creates an extra via POST with the full backend contract", async () => {
    installReads();
    let created = false;
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/extras", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        created = true;
        return HttpResponse.json({ id: 12, property: 7, name: "Cleaning", amount: "50" });
      }),
      // After invalidation the list refetches — return the new row too.
      http.get("/api/v1/properties/7/extras", () =>
        HttpResponse.json(
          drfPage(created ? [extra, { ...extra, id: 12, name: "Cleaning" }] : [extra]),
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Add extra" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Cleaning");
    await user.type(within(dialog).getByLabelText("Amount"), "50");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    // Full-body equality, not a subset assert — a subset is exactly how the
    // required-`property` / `min_nights:null` regressions slipped past tests.
    // Read-only currency_code is never written, `property` comes from the URL,
    // absent dates go as explicit null.
    expect(posted[0]).toEqual({
      name: "Cleaning",
      description: "",
      kind: "other",
      calc: "fixed_per_stay",
      amount: "50",
      currency: 1,
      is_mandatory: false,
      applies_from: null,
      applies_to: null,
      is_active: true,
    });
    expect("property" in posted[0]).toBe(false);
    expect(await screen.findByText("Cleaning")).toBeInTheDocument();
  });

  it("creates a discount via POST with rule_kind, kind, amount, dates and null code", async () => {
    installReads();
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/discounts", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ id: 22, property: 7, name: "Long stay", amount: "15" });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Add discount" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Long stay");
    await user.type(within(dialog).getByLabelText("Amount"), "15");
    await user.type(within(dialog).getByLabelText("Valid from"), "2026-06-01");
    await user.type(within(dialog).getByLabelText("Valid to"), "2026-09-30");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      name: "Long stay",
      rule_kind: "promo_code",
      kind: "percent",
      amount: "15",
      valid_from: "2026-06-01",
      valid_to: "2026-09-30",
    });
    // An empty promo code is sent as null (a "" would collide on the UNIQUE index).
    expect(posted[0].code).toBeNull();
    // uses_count is read-only and must never be written.
    expect(posted[0].uses_count).toBeUndefined();
  });

  it("edits a discount via PATCH to the flat detail route", async () => {
    installReads();
    const patched: Array<{ id: string; body: unknown }> = [];
    server.use(
      http.patch("/api/v1/discounts/:id", async ({ params, request }) => {
        patched.push({ id: String(params.id), body: await request.json() });
        return HttpResponse.json({ ...discount, name: "Early bird 2" });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    const row = (await screen.findByText("Early bird")).closest("li");
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Early bird 2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0].id).toBe("21");
    expect(patched[0].body).toMatchObject({ name: "Early bird 2" });
  });

  it("deletes an inclusion via DELETE after confirm", async () => {
    installReads();
    const deleted: string[] = [];
    server.use(
      http.delete("/api/v1/services/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    // First "Delete" icon button belongs to the inclusions section (rendered first).
    await user.click((await screen.findAllByRole("button", { name: "Delete" }))[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleted).toEqual(["9"]));
  });

  it("disables the Add buttons for a read-only user", async () => {
    installReads();
    renderPanel(false);
    await screen.findByText("Daily maid");
    expect(screen.getByRole("button", { name: "Add inclusion" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add extra" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add discount" })).toBeDisabled();
    // No per-row edit/delete affordances either.
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });
});
