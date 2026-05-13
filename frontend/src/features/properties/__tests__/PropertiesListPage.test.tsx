import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
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
});
