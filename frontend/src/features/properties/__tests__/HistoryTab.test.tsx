import { http, HttpResponse } from "msw";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { HistoryTab } from "../tabs/HistoryTab";
import type { PropertyDetail } from "../schemas";

const propertyFixture = {
  id: 5,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

function asAdmin() {
  useAuthStore.setState({
    user: null,
    role: "ADMIN",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function asNonAdmin() {
  useAuthStore.setState({
    user: null,
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

afterEach(() => {
  server.resetHandlers();
  // Reset the module-global auth store so role state can't leak between tests.
  useAuthStore.getState().clear();
});

describe("property HistoryTab", () => {
  it("queries both the property and its finance audit trails (finance pk == property id)", async () => {
    const entityTypes: string[] = [];
    const entityIds: (string | null)[] = [];
    server.use(
      http.get("/api/v1/audit-log", ({ request }) => {
        const params = new URL(request.url).searchParams;
        entityTypes.push(params.get("entity_type") ?? "");
        entityIds.push(params.get("entity_id"));
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );

    const context = { property: { id: 5 } as PropertyDetail };
    renderWithProviders(
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/x" element={<HistoryTab />} />
        </Route>
      </Routes>,
      { route: "/x" },
    );

    await waitFor(() => expect(entityTypes.length).toBeGreaterThanOrEqual(2));
    expect(entityTypes).toContain("properties.property");
    expect(entityTypes).toContain("properties.propertyfinance");
    // every panel must target the property's own id (finance pk == property id).
    // Asserted out here, not inside the resolver, so a wrong id fails the test
    // rather than turning into an error response MSW swallows.
    expect(entityIds.every((id) => id === "5")).toBe(true);
    expect(entityIds.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Record changes")).toBeInTheDocument();
    expect(screen.getByText(/Finance changes/i)).toBeInTheDocument();
  });
});

describe("property History tab nav gating", () => {
  beforeEach(() => {
    server.use(http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)));
  });

  function setup(route = "/properties/casa-norte/details") {
    return renderWithProviders(
      <Routes>
        <Route path="/properties/:id" element={<PropertyDetailLayout />}>
          <Route index element={<Navigate to="details" replace />} />
          <Route path="details" element={<div>Details stub</div>} />
          <Route path="history" element={<HistoryTab />} />
        </Route>
      </Routes>,
      { route },
    );
  }

  it("shows the History tab to an admin", async () => {
    asAdmin();
    setup();
    await waitFor(() => expect(screen.getAllByText("Casa Norte").length).toBeGreaterThan(0));
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });

  it("hides the History tab from a non-admin", async () => {
    asNonAdmin();
    setup();
    await waitFor(() => expect(screen.getAllByText("Casa Norte").length).toBeGreaterThan(0));
    expect(screen.queryByRole("link", { name: "History" })).not.toBeInTheDocument();
  });
});
