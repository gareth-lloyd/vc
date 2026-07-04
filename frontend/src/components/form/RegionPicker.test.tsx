import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { drfPage } from "@/test/drf";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { RegionPicker } from "./RegionPicker";

const regions = [
  { id: 7, country: 1, country_iso2: "ES", name: "Ibiza", slug: "ibiza", is_active: true },
  { id: 9, country: 1, country_iso2: "ES", name: "Mallorca", slug: "mallorca", is_active: false },
  { id: 11, country: 2, country_iso2: "GR", name: "Crete", slug: "crete", is_active: true },
];

function installRegions() {
  server.use(http.get("/api/v1/regions", () => HttpResponse.json(drfPage(regions))));
}

async function openPicker() {
  const trigger = await screen.findByRole("combobox");
  await userEvent.click(trigger);
}

describe("RegionPicker", () => {
  it("offers only active regions of the scoped country (case-insensitive iso2)", async () => {
    installRegions();
    renderWithProviders(<RegionPicker value={null} onChange={() => {}} countryIso2="es" />);
    await openPicker();
    expect(await screen.findByRole("option", { name: "Ibiza" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Crete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Mallorca/ })).not.toBeInTheDocument();
  });

  it("scopes by country id too", async () => {
    installRegions();
    renderWithProviders(<RegionPicker value={null} onChange={() => {}} countryId={2} />);
    await openPicker();
    expect(await screen.findByRole("option", { name: "Crete" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Ibiza/ })).not.toBeInTheDocument();
  });

  it("keeps the current value visible even when inactive or out of scope", async () => {
    installRegions();
    // Crete (GR) is the current value while the picker is scoped to ES.
    renderWithProviders(<RegionPicker value={11} onChange={() => {}} countryIso2="ES" />);
    await openPicker();
    expect(await screen.findByRole("option", { name: /Crete/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ibiza" })).toBeInTheDocument();
  });

  it("disambiguates with the country ISO when unscoped", async () => {
    installRegions();
    renderWithProviders(<RegionPicker value={null} onChange={() => {}} />);
    await openPicker();
    expect(await screen.findByRole("option", { name: "Ibiza (ES)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Crete (GR)" })).toBeInTheDocument();
  });

  it("offers an All-regions row that clears the value when clearable", async () => {
    installRegions();
    let picked: number | null = 7;
    renderWithProviders(
      <RegionPicker value={7} onChange={(id) => (picked = id)} countryIso2="ES" clearable />,
    );
    await openPicker();
    await userEvent.click(await screen.findByRole("option", { name: "All regions" }));
    expect(picked).toBeNull();
  });

  it("reports the picked region id as a number", async () => {
    installRegions();
    let picked: number | null = null;
    renderWithProviders(
      <RegionPicker value={null} onChange={(id) => (picked = id)} countryIso2="ES" />,
    );
    await openPicker();
    await userEvent.click(await screen.findByRole("option", { name: "Ibiza" }));
    expect(picked).toBe(7);
  });
});
