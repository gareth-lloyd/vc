import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { SuppliersListPage } from "../SuppliersListPage";

const fixture = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 7,
      first_name: "Helga",
      last_name: "Keeper",
      agency: null,
      agency_detail: null,
      status: "active",
      kind: "contact",
      // A supplier holding two property roles — and a stray "customer" capacity
      // that must NOT show in the role column.
      contact_types: ["housekeeper", "management_company", "customer"],
      emails: [],
      phones: [],
    },
  ],
};

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/contacts" element={<SuppliersListPage />} />
    </Routes>,
    { route: "/contacts" },
  );
}

describe("SuppliersListPage", () => {
  it("pins ?directory=suppliers on the contacts request (GAP-048)", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("directory"));
        return HttpResponse.json(fixture);
      }),
    );
    renderPage();
    await screen.findByText("Helga Keeper");
    await waitFor(() => expect(seen).toContain("suppliers"));
  });

  it("renders the property role column and hides the kind filter", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(fixture)));
    renderPage();
    await screen.findByText("Helga Keeper");

    // Role chips come from the property-role subset of contact_types; the
    // synthetic "customer" capacity is excluded.
    expect(screen.getByText("Housekeeper")).toBeInTheDocument();
    expect(screen.getByText("Management Company")).toBeInTheDocument();
    expect(screen.queryByText("Customer")).not.toBeInTheDocument();

    // The kind filter is meaningless on a kind=CONTACT-scoped list — hidden here.
    expect(screen.queryByRole("combobox", { name: /filter by type/i })).not.toBeInTheDocument();
  });

  it("titles the page Suppliers", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(fixture)));
    renderPage();
    expect(await screen.findByRole("heading", { name: "Suppliers" })).toBeInTheDocument();
  });

  it("drops a stale ?kind= param so it can't silently empty the list", async () => {
    // The kind filter UI is hidden here, so a leftover `?kind=customer` from an
    // old link must NOT be forwarded — it would AND with the forced kind=CONTACT
    // and return nothing, with no control to clear it.
    const seenKind: (string | null)[] = [];
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        seenKind.push(new URL(request.url).searchParams.get("kind"));
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<SuppliersListPage />} />
      </Routes>,
      { route: "/contacts?kind=customer" },
    );
    await screen.findByText("Helga Keeper");
    await waitFor(() => expect(seenKind.length).toBeGreaterThan(0));
    expect(seenKind.every((k) => k === null)).toBe(true);
  });
});
