import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { ExtraFormDialog } from "../components/ExtraFormDialog";

const gbpCurrency = {
  id: 5,
  code: "GBP",
  name: "Pound Sterling",
  symbol: "£",
  decimal_places: 2,
  is_active: true,
};

function installReads(settingsCurrency: number | null) {
  server.use(
    http.get("/api/v1/properties/7/settings", () =>
      HttpResponse.json({ property: 7, currency: settingsCurrency, currency_code: null }),
    ),
    // Listed so the CurrencyPicker can render the seeded value.
    http.get("/api/v1/currencies", () => HttpResponse.json(drfPage([gbpCurrency]))),
  );
}

async function fillAndSave(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText("Name"), "Cleaning");
  await user.type(within(dialog).getByLabelText("Amount"), "50");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
}

describe("ExtraFormDialog currency default", () => {
  it("seeds the currency from the season FK id when settings has no currency FK", async () => {
    // The seeded GBP property has a null `settings.currency` FK but the pricing
    // currency lives on the season (its `currency` FK id, passed as
    // `defaultCurrencyId`). The POST must carry that FK — otherwise the picker
    // opens empty and the required-field save is rejected.
    installReads(null);
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/extras", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ id: 12, property: 7, name: "Cleaning", amount: "50" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <ExtraFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
        defaultCurrencyId={5}
      />,
    );

    await fillAndSave(user);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ name: "Cleaning", amount: "50", currency: 5 });
  });

  it("prefers the settings currency FK over the season default when both are set", async () => {
    // Precedence must be deterministic (settings FK wins), not a race on which
    // query resolves first.
    installReads(9);
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/properties/7/extras", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ id: 12, property: 7, name: "Cleaning", amount: "50" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <ExtraFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
        defaultCurrencyId={5}
      />,
    );

    await fillAndSave(user);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ currency: 9 });
  });
});

describe("ExtraFormDialog commissionable (GAP-076)", () => {
  function installPost(posted: Array<Record<string, unknown>>) {
    server.use(
      http.post("/api/v1/properties/7/extras", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ id: 12, property: 7, name: "Cleaning", amount: "50" });
      }),
    );
  }

  it("defaults to commissionable and sends commissionable: true on create", async () => {
    installReads(5);
    const posted: Array<Record<string, unknown>> = [];
    installPost(posted);

    const user = userEvent.setup();
    renderWithProviders(
      <ExtraFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
        defaultCurrencyId={5}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("checkbox", { name: "Commissionable" })).toBeChecked();
    await fillAndSave(user);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ commissionable: true });
  });

  it("sends commissionable: false when the checkbox is unticked", async () => {
    installReads(5);
    const posted: Array<Record<string, unknown>> = [];
    installPost(posted);

    const user = userEvent.setup();
    renderWithProviders(
      <ExtraFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
        defaultCurrencyId={5}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox", { name: "Commissionable" }));
    await fillAndSave(user);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ commissionable: false });
  });
});

describe("ExtraFormDialog currency mismatch hint", () => {
  function renderCreate(planCurrencyIds: number[] | undefined) {
    installReads(5);
    return renderWithProviders(
      <ExtraFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
        defaultCurrencyId={5}
        planCurrencyIds={planCurrencyIds}
      />,
    );
  }

  it("warns when the chosen currency is not used by any rate plan", async () => {
    renderCreate([9]);
    expect(
      await screen.findByText(
        "No rate plan uses this currency, so the pricing engine will never apply this extra to a quote.",
      ),
    ).toBeInTheDocument();
  });

  it("shows no warning when the currency matches a plan currency", async () => {
    renderCreate([5, 9]);
    // Wait for the seeded currency (5/GBP) to actually land in the picker —
    // only then does the mismatch predicate run against a real value.
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("combobox", { name: "Currency" })).toHaveTextContent("GBP"),
    );
    expect(screen.queryByText(/never apply this extra/)).not.toBeInTheDocument();
  });

  it("shows no warning when plan currencies are unknown", async () => {
    renderCreate(undefined);
    await screen.findByRole("dialog");
    expect(screen.queryByText(/never apply this extra/)).not.toBeInTheDocument();
  });
});
