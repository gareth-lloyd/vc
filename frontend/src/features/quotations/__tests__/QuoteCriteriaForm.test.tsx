import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { QuoteCriteriaForm } from "../components/QuoteCriteriaForm";

const countries = [
  { id: 1, iso2: "ES", name: "Spain", is_active: true },
  { id: 2, iso2: "GR", name: "Greece", is_active: true },
];

const regions = [
  { id: 7, country: 1, country_iso2: "ES", name: "Ibiza", slug: "ibiza" },
  { id: 9, country: 1, country_iso2: "ES", name: "Mallorca", slug: "mallorca" },
  { id: 11, country: 2, country_iso2: "GR", name: "Crete", slug: "crete" },
];

// The selects must only offer geo values that can match a property, so both
// lookups are fetched with `has_properties=true`; capture the params to pin it.
function installGeoHandlers(seen?: { countries: string[]; regions: string[] }) {
  server.use(
    http.get("/api/v1/countries", ({ request }) => {
      seen?.countries.push(new URL(request.url).search);
      return HttpResponse.json(drfPage(countries));
    }),
    http.get("/api/v1/regions", ({ request }) => {
      seen?.regions.push(new URL(request.url).search);
      return HttpResponse.json(drfPage(regions));
    }),
  );
}

function renderForm(onSubmit = vi.fn()) {
  renderWithProviders(
    <QuoteCriteriaForm
      initial={{ date_from: "2026-07-01", date_to: "2026-07-08" }}
      isSubmitting={false}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

async function openSelect(name: RegExp) {
  const trigger = await screen.findByRole("combobox", { name });
  await userEvent.click(trigger);
  return trigger;
}

describe("QuoteCriteriaForm geo selects", () => {
  it("offers in-use countries from the API plus an Any option", async () => {
    const seen = { countries: [] as string[], regions: [] as string[] };
    installGeoHandlers(seen);
    renderForm();

    await openSelect(/country/i);
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "All countries" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Spain" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Greece" })).toBeInTheDocument();

    await waitFor(() => expect(seen.countries.length).toBeGreaterThan(0));
    await waitFor(() => expect(seen.regions.length).toBeGreaterThan(0));
    expect(seen.countries[0]).toContain("has_properties=true");
    expect(seen.regions[0]).toContain("has_properties=true");
  });

  it("labels regions with their country ISO while no country is chosen", async () => {
    installGeoHandlers();
    renderForm();

    await openSelect(/region/i);
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "Ibiza (ES)" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Crete (GR)" })).toBeInTheDocument();
  });

  it("narrows region options to the selected country", async () => {
    installGeoHandlers();
    renderForm();

    await openSelect(/country/i);
    await userEvent.click(await screen.findByRole("option", { name: "Spain" }));

    await openSelect(/region/i);
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "Ibiza" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Mallorca" })).toBeInTheDocument();
    expect(within(listbox).queryByRole("option", { name: /Crete/ })).not.toBeInTheDocument();
  });

  it("resets an incompatible region when the country changes", async () => {
    installGeoHandlers();
    const onSubmit = renderForm();

    await openSelect(/region/i);
    await userEvent.click(await screen.findByRole("option", { name: "Crete (GR)" }));

    await openSelect(/country/i);
    await userEvent.click(await screen.findByRole("option", { name: "Spain" }));

    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ country: "ES", region: "" });
  });

  it("keeps a compatible region and submits iso2 + region id", async () => {
    installGeoHandlers();
    const onSubmit = renderForm();

    await openSelect(/country/i);
    await userEvent.click(await screen.findByRole("option", { name: "Spain" }));

    await openSelect(/region/i);
    await userEvent.click(await screen.findByRole("option", { name: "Ibiza" }));

    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ country: "ES", region: "7" });
  });

  it("submits empty strings when both stay on Any", async () => {
    installGeoHandlers();
    const onSubmit = renderForm();

    await userEvent.click(await screen.findByRole("button", { name: /search/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ country: "", region: "" });
  });
});
