import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { CompaniesListPage } from "../CompaniesListPage";

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      name: "Analytical Engines",
      org_type: "agency",
      status: "active",
      email: "ada@example.com",
      phone: null,
      town: "London",
    },
    {
      id: 2,
      name: "Solo Travel Co",
      org_type: "agency",
      status: "inactive",
      email: null,
      phone: null,
      town: "Athens",
    },
  ],
};

describe("CompaniesListPage", () => {
  it("renders rows from /organisations scoped to org_type=agency", async () => {
    let capturedOrgType: string | null = null;
    server.use(
      http.get("/api/v1/organisations", ({ request }) => {
        capturedOrgType = new URL(request.url).searchParams.get("org_type");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/companies" element={<CompaniesListPage />} />
      </Routes>,
      { route: "/companies" },
    );
    expect(await screen.findByText("Analytical Engines")).toBeInTheDocument();
    expect(screen.getByText("Solo Travel Co")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(capturedOrgType).toBe("agency");
  });

  it("renders an empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/organisations", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/companies" element={<CompaniesListPage />} />
      </Routes>,
      { route: "/companies" },
    );
    expect(await screen.findByText(/no companies match/i)).toBeInTheDocument();
  });

  it("shows an error state on 500 and retries", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/organisations", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/companies" element={<CompaniesListPage />} />
      </Routes>,
      { route: "/companies" },
    );
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("Analytical Engines")).toBeInTheDocument();
  });

  it("debounces search and forwards `search` to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/organisations", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("search") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/companies" element={<CompaniesListPage />} />
      </Routes>,
      { route: "/companies" },
    );
    await screen.findByText("Analytical Engines");
    await userEvent.type(screen.getByLabelText(/search/i), "engines");
    await waitFor(() => expect(seen).toContain("engines"));
  });

  it("navigates to the detail page on row click", async () => {
    server.use(http.get("/api/v1/organisations", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/companies" element={<CompaniesListPage />} />
        <Route path="/companies/:id" element={<div>Detail: engines</div>} />
      </Routes>,
      { route: "/companies" },
    );
    await userEvent.click(await screen.findByText("Analytical Engines"));
    await waitFor(() => expect(screen.getByText("Detail: engines")).toBeInTheDocument());
  });
});
