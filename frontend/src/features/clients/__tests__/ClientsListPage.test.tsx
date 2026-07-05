import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { ClientsListPage } from "../ClientsListPage";

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      title: "Ms",
      first_name: "Ada",
      last_name: "Lovelace",
      primary_email: "ada@example.com",
      primary_phone: "+44 7700 900111",
      is_agent: false,
      status: "active",
      quoted_region_slugs: [],
      booked_region_slugs: [],
    },
    {
      id: 2,
      title: "",
      first_name: "Grace",
      last_name: "Hopper",
      primary_email: null,
      primary_phone: null,
      is_agent: true,
      status: "inactive",
      quoted_region_slugs: [],
      booked_region_slugs: [],
    },
  ],
};

function renderList(extraRoutes?: React.ReactNode) {
  return renderWithProviders(
    <Routes>
      <Route path="/clients" element={<ClientsListPage />} />
      {extraRoutes}
    </Routes>,
    { route: "/clients" },
  );
}

describe("ClientsListPage", () => {
  // The region-chip cells fire useRegions(); give every test a default handler
  // (fixtures use empty region arrays, so an empty page suffices).
  beforeEach(() => {
    server.use(http.get("/api/v1/regions", () => HttpResponse.json(drfPage([]))));
  });

  it("renders renter rows with capacity badges", async () => {
    server.use(http.get("/api/v1/clients", () => HttpResponse.json(fixture)));
    renderList();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    // Ada is direct, Grace is an agent client.
    expect(screen.getByText("Direct")).toBeInTheDocument();
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  it("renders quoted/booked region chips by name", async () => {
    server.use(
      http.get("/api/v1/regions", () =>
        HttpResponse.json(
          drfPage([{ id: 7, country: 1, name: "Tuscany", slug: "tuscany", is_active: true }]),
        ),
      ),
      http.get("/api/v1/clients", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              ...fixture.results[0],
              quoted_region_slugs: ["tuscany"],
              booked_region_slugs: ["tuscany"],
            },
          ],
        }),
      ),
    );
    renderList();
    // Tuscany shows in both the quoted and booked columns for the row.
    expect(await screen.findAllByText("Tuscany")).toHaveLength(2);
  });

  it("renders an empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/clients", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderList();
    expect(await screen.findByText(/no clients match/i)).toBeInTheDocument();
  });

  it("shows an error state on 500 and retries", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/clients", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("debounces search and forwards `search` to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("search") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.type(screen.getByLabelText(/search/i), "lovelace");
    await waitFor(() => expect(seen).toContain("lovelace"));
  });

  it("forwards the capacity filter to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("capacity") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByLabelText(/filter by channel/i));
    await userEvent.click(await screen.findByRole("option", { name: "Agent" }));
    await waitFor(() => expect(seen).toContain("agent"));
  });

  it("forwards the status filter to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("status") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByLabelText(/filter by status/i));
    await userEvent.click(await screen.findByRole("option", { name: "Inactive" }));
    await waitFor(() => expect(seen).toContain("inactive"));
  });

  it("toggles the VIP chip and forwards tags to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("tags") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByRole("button", { name: /vip/i }));
    await waitFor(() => expect(seen).toContain("vip"));
  });

  it("composes the VIP and Trade chips into a comma list", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("tags") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByRole("button", { name: /vip/i }));
    await userEvent.click(screen.getByRole("button", { name: /trade/i }));
    await waitFor(() => expect(seen).toContain("vip,trade"));
  });

  it("toggles the Repeat chip and forwards repeat=true", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("repeat") ?? "");
        return HttpResponse.json(fixture);
      }),
    );
    renderList();
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByRole("button", { name: /repeat/i }));
    await waitFor(() => expect(seen).toContain("true"));
  });

  it("reflects the active chips from the URL", async () => {
    server.use(http.get("/api/v1/clients", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/clients" element={<ClientsListPage />} />
      </Routes>,
      { route: "/clients?tags=vip&repeat=true" },
    );
    await screen.findByText("Ada Lovelace");
    expect(screen.getByRole("button", { name: /vip/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /trade/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /repeat/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("hydrates a multi-tag URL back into both pressed chips", async () => {
    server.use(http.get("/api/v1/clients", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/clients" element={<ClientsListPage />} />
      </Routes>,
      { route: "/clients?tags=vip,trade" },
    );
    await screen.findByText("Ada Lovelace");
    expect(screen.getByRole("button", { name: /vip/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /trade/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("navigates to the client detail page on row click", async () => {
    server.use(http.get("/api/v1/clients", () => HttpResponse.json(fixture)));
    renderList(<Route path="/clients/:id" element={<div>Client detail</div>} />);
    await userEvent.click(await screen.findByText("Ada Lovelace"));
    await waitFor(() => expect(screen.getByText("Client detail")).toBeInTheDocument());
  });
});
