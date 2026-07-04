import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { PropertiesListPage } from "../PropertiesListPage";

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: "Casa Norte", slug: "casa-norte", status: "active" },
    { id: 2, name: "Villa Azul", slug: "villa-azul", status: "draft" },
  ],
};

describe("PropertiesListPage", () => {
  // The page calls useRegions() and useCountries() unconditionally, so every
  // test fires GET /regions + GET /countries. Stub them here (MSW runs
  // onUnhandledRequest:"error"); the global afterEach resetHandlers re-arms
  // this before each test.
  beforeEach(() => {
    server.use(
      http.get("/api/v1/regions", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 7,
              country: 1,
              country_iso2: "ES",
              name: "Ibiza",
              slug: "ibiza-7",
              is_active: true,
            },
            {
              id: 9,
              country: 1,
              country_iso2: "ES",
              name: "Mallorca",
              slug: "mallorca-9",
              is_active: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/countries", () =>
        HttpResponse.json(
          drfPage([
            { id: 1, iso2: "ES", name: "Spain", is_active: true },
            { id: 3, iso2: "HR", name: "Croatia", is_active: true },
          ]),
        ),
      ),
    );
  });

  it("renders rows from /properties", async () => {
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    expect(await screen.findByText("Casa Norte")).toBeInTheDocument();
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
  });

  it("renders an empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    expect(await screen.findByText(/no properties match/i)).toBeInTheDocument();
  });

  it("shows an error state on 500 and retries", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/properties", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("Casa Norte")).toBeInTheDocument();
  });

  it("debounces search and forwards q to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("q") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    await screen.findByText("Casa Norte");
    await userEvent.type(screen.getByLabelText(/search/i), "casa");
    await waitFor(() => expect(seen).toContain("casa"));
  });

  it("navigates to the detail page on row click", async () => {
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
        <Route path="/properties/:id/details" element={<div>Detail: casa-norte</div>} />
      </Routes>,
      { route: "/properties" },
    );
    await userEvent.click(await screen.findByText("Casa Norte"));
    await waitFor(() => expect(screen.getByText("Detail: casa-norte")).toBeInTheDocument());
  });

  it("falls back to numeric id when slug is whitespace-only", async () => {
    const whitespaceSlugs = {
      ...fixture,
      results: [{ id: 42, name: "Blank Slug Villa", slug: "   ", status: "active" }],
      count: 1,
    };
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(whitespaceSlugs)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
        <Route path="/properties/:id/details" element={<div>Detail: 42</div>} />
      </Routes>,
      { route: "/properties" },
    );
    await userEvent.click(await screen.findByText("Blank Slug Villa"));
    await waitFor(() => expect(screen.getByText("Detail: 42")).toBeInTheDocument());
  });

  it("falls back to numeric id when slug is a full URL", async () => {
    const urlSlugs = {
      ...fixture,
      results: [
        {
          id: 436,
          name: "URL Slug Villa",
          slug: "https://www.villacollective.com/mallorca/-436",
          status: "active",
        },
      ],
      count: 1,
    };
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(urlSlugs)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
        <Route path="/properties/:id/details" element={<div>Detail: 436</div>} />
      </Routes>,
      { route: "/properties" },
    );
    await userEvent.click(await screen.findByText("URL Slug Villa"));
    await waitFor(() => expect(screen.getByText("Detail: 436")).toBeInTheDocument());
  });

  it("renders the region filter", async () => {
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    await screen.findByText("Casa Norte");
    expect(screen.getByRole("combobox", { name: /filter by region/i })).toBeInTheDocument();
  });

  it("populates the country filter from the API and forwards the iso2", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("country") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    await screen.findByText("Casa Norte");
    await userEvent.click(screen.getByRole("combobox", { name: /filter by country/i }));
    // Croatia is not in the old hardcoded 5-country list — it must appear the
    // moment the API offers it (labels come from the API name field).
    await userEvent.click(await screen.findByRole("option", { name: "Croatia" }));
    await waitFor(() => expect(seen).toContain("HR"));
  });

  it("renders a lowercase bookmarked country as the selected option", async () => {
    server.use(http.get("/api/v1/properties", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties?country=es" },
    );
    await screen.findByText("Casa Norte");
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /filter by country/i })).toHaveTextContent(
        "Spain",
      ),
    );
  });

  it("forwards region to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("region") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/properties" element={<PropertiesListPage />} />
      </Routes>,
      { route: "/properties" },
    );
    await screen.findByText("Casa Norte");
    await userEvent.click(screen.getByRole("combobox", { name: /filter by region/i }));
    // Label disambiguates by country; value forwarded is the region id.
    await userEvent.click(await screen.findByRole("option", { name: "Ibiza (ES)" }));
    await waitFor(() => expect(seen).toContain("7"));
  });
});
