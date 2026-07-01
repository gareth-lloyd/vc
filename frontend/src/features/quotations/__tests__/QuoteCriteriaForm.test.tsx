import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { geoLookupHandlers } from "@/test/msw/handlers";
import { QuoteCriteriaForm } from "../components/QuoteCriteriaForm";

afterEach(() => server.resetHandlers());

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

async function openSelect(name: RegExp) {
  const trigger = await screen.findByRole("combobox", { name });
  await userEvent.click(trigger);
  return trigger;
}

describe("QuoteCriteriaForm", () => {
  function renderRange(onSubmit = vi.fn(), initial: Record<string, unknown> = {}) {
    server.use(...geoLookupHandlers);
    renderWithProviders(
      <QuoteCriteriaForm initial={initial} isSubmitting={false} onSubmit={onSubmit} />,
    );
    return onSubmit;
  }

  it("submits the arrival window + weeks translated to the wire criteria", async () => {
    const onSubmit = renderRange();

    await userEvent.type(screen.getByLabelText(/arrive from/i), "2026-07-04");
    await userEvent.type(screen.getByLabelText(/arrive to/i), "2026-07-10");
    await userEvent.click(screen.getByRole("button", { name: /increase number of weeks/i }));
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    // W = 6 → flex 3, preferred arrival at the midpoint; 2 weeks = 14 nights.
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          date_from: "2026-07-07",
          date_to: "2026-07-21",
          flex_days: 3,
          adults: 2,
        }),
      ),
    );
  });

  it("hides Arrive-to when Search Specific Date is on and sends flex 0", async () => {
    const onSubmit = renderRange(vi.fn(), {
      arrive_from: "2026-07-04",
      arrive_to: "2026-07-10",
    });

    expect(screen.getByLabelText(/arrive to/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /search specific date/i }));
    expect(screen.queryByLabelText(/arrive to/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          date_from: "2026-07-04",
          date_to: "2026-07-11",
          flex_days: 0,
        }),
      ),
    );
  });

  it("blocks submit with an inline error when the window exceeds 42 days", async () => {
    const onSubmit = renderRange();

    await userEvent.type(screen.getByLabelText(/arrive from/i), "2026-06-01");
    await userEvent.type(screen.getByLabelText(/arrive to/i), "2026-07-14");
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at most 42 days/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("steps weeks down to a floor of one", async () => {
    renderRange();

    const decrease = screen.getByRole("button", { name: /decrease number of weeks/i });
    expect(screen.getByText(/1 week$/i)).toBeInTheDocument();
    expect(decrease).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /increase number of weeks/i }));
    expect(screen.getByText(/2 weeks/i)).toBeInTheDocument();
    expect(decrease).toBeEnabled();
  });

  it("seeds from the provided initial values", () => {
    renderRange(vi.fn(), {
      arrive_from: "2026-07-01",
      arrive_to: "2026-07-07",
      weeks: 2,
      specific_date: false,
      adults: 4,
    });

    expect(screen.getByLabelText(/arrive from/i)).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/arrive to/i)).toHaveValue("2026-07-07");
    expect(screen.getByText(/2 weeks/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/adults/i)).toHaveValue(4);
  });
});

describe("QuoteCriteriaForm geo selects", () => {
  function renderForm(onSubmit = vi.fn()) {
    renderWithProviders(
      <QuoteCriteriaForm
        initial={{ arrive_from: "2026-07-01", arrive_to: "2026-07-08" }}
        isSubmitting={false}
        onSubmit={onSubmit}
      />,
    );
    return onSubmit;
  }

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
