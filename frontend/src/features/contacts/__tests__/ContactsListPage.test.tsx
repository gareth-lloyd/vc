import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactsListPage } from "../ContactsListPage";

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      first_name: "Ada",
      last_name: "Lovelace",
      agency: 100,
      agency_detail: { id: 100, name: "Analytical Engines", org_type: "agency", status: "active" },
      status: "active",
      kind: "customer",
      emails: [{ id: 11, email: "ada@example.com", is_primary: true }],
      phones: [],
    },
    {
      id: 2,
      first_name: null,
      last_name: null,
      agency: 200,
      agency_detail: { id: 200, name: "Solo Corp", org_type: "agency", status: "active" },
      status: "active",
      kind: "contact",
      emails: [],
      phones: [],
    },
  ],
};

describe("ContactsListPage", () => {
  it("renders rows from /contacts", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Solo Corp")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("renders an empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/contacts", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    expect(await screen.findByText(/no contacts match/i)).toBeInTheDocument();
  });

  it("shows an error state on 500 and retries", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/contacts", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("debounces search and forwards the term as `search` to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("search") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    await screen.findByText("Ada Lovelace");
    await userEvent.type(screen.getByLabelText(/search/i), "ada");
    await waitFor(() => expect(seen).toContain("ada"));
  });

  it("forwards the selected kind to the API", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("kind"));
        return HttpResponse.json(fixture);
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByRole("combobox", { name: /filter by type/i }));
    await userEvent.click(await screen.findByRole("option", { name: /^customer$/i }));
    await waitFor(() => expect(seen).toContain("customer"));
  });

  it("renders the kind of each row", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
      </Routes>,
      { route: "/contacts" },
    );
    await screen.findByText("Ada Lovelace");
    // The kind column shows the localised label, distinguishing customers from
    // business contacts (GAP-045 D3-4).
    expect(screen.getByText("Customer")).toBeInTheDocument();
    expect(screen.getByText("Contact")).toBeInTheDocument();
  });

  it("navigates to the detail page on row click", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsListPage />} />
        <Route path="/contacts/:id" element={<div>Detail: ada</div>} />
      </Routes>,
      { route: "/contacts" },
    );
    await userEvent.click(await screen.findByText("Ada Lovelace"));
    await waitFor(() => expect(screen.getByText("Detail: ada")).toBeInTheDocument());
  });
});
