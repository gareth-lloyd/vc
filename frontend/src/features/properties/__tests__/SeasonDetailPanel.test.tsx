import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { SeasonDetailPanel } from "../components/SeasonDetailPanel";

function installSeason(currencyCode: string | null) {
  server.use(
    http.get("/api/v1/seasons/11", () =>
      HttpResponse.json({
        id: 11,
        property: 5,
        name: "Summer 2026",
        currency: 42,
        currency_code: currencyCode,
        price_basis: "gross",
        effective_from: "2026-06-01",
        effective_to: "2026-09-30",
        is_active: true,
        periods: [],
      }),
    ),
  );
}

function installSettings(currencyCode: string | null) {
  server.use(
    http.get("/api/v1/properties/5/settings", () =>
      HttpResponse.json({
        property: 5,
        currency: null,
        currency_code: currencyCode,
        changeover_day: null,
        min_nights_rental: null,
        timezone: null,
      }),
    ),
  );
}

function renderPanel() {
  return renderWithProviders(
    <SeasonDetailPanel propertyId={5} seasonId={11} onBack={() => {}} canWrite={false} />,
  );
}

describe("SeasonDetailPanel — currency mismatch warning (GAP-026)", () => {
  it("warns (non-blocking) when the season currency differs from the property's", async () => {
    installSeason("EUR");
    installSettings("GBP");
    renderPanel();

    const warning = await screen.findByRole("status");
    expect(warning).toHaveTextContent(/prices in EUR/i);
    expect(warning).toHaveTextContent(/currency is GBP/i);
  });

  it("shows no warning when the currencies match", async () => {
    installSeason("EUR");
    installSettings("EUR");
    renderPanel();

    expect(await screen.findByText("Summer 2026")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows no warning when the property has no effective currency", async () => {
    installSeason("EUR");
    installSettings(null);
    renderPanel();

    expect(await screen.findByText("Summer 2026")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
