import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { EnquiriesListPage } from "../EnquiriesListPage";

const baseEnquiry = {
  id: 1,
  reference: "E-AAA-001",
  status: "new" as const,
  guest: null,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  property: 12,
  region: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  request_type: "quote" as const,
  assigned_to: null,
  agent: null,
  site_source: "main_website" as const,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

const listFixture = {
  count: 3,
  next: null,
  previous: null,
  results: [
    baseEnquiry,
    {
      ...baseEnquiry,
      id: 2,
      reference: "E-BBB-002",
      status: "contacted" as const,
      first_name: "Grace",
      last_name: "Hopper",
      email: "grace@example.com",
    },
    {
      ...baseEnquiry,
      id: 3,
      reference: "E-CCC-003",
      status: "quoted" as const,
      first_name: "Linus",
      last_name: "Torvalds",
      email: "linus@example.com",
    },
  ],
};

function setup(route = "/enquiries") {
  return renderWithProviders(
    <Routes>
      <Route path="/enquiries" element={<EnquiriesListPage />} />
      <Route path="/enquiries/:id/details" element={<div>Detail page</div>} />
    </Routes>,
    { route },
  );
}

describe("EnquiriesListPage", () => {
  it("renders the Kanban board by default with cards in their status columns", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup();

    await screen.findByTestId("kanban-column-new");
    const newCol = screen.getByTestId("kanban-column-new");
    const contactedCol = screen.getByTestId("kanban-column-contacted");
    const quotedCol = screen.getByTestId("kanban-column-quoted");

    expect(within(newCol).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(contactedCol).getByText("Grace Hopper")).toBeInTheDocument();
    expect(within(quotedCol).getByText("Linus Torvalds")).toBeInTheDocument();
  });

  it("toggles to the list view and renders a table", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup();

    await screen.findByTestId("kanban-column-new");
    await userEvent.click(screen.getByRole("tab", { name: /list/i }));

    expect(await screen.findByText("E-AAA-001")).toBeInTheDocument();
    expect(screen.getByText("E-BBB-002")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-column-new")).not.toBeInTheDocument();
  });

  it("debounces search and forwards q to the API", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.get("q") ?? "");
        return HttpResponse.json(listFixture);
      }),
    );
    setup();

    await screen.findByTestId("kanban-column-new");
    await userEvent.type(screen.getByLabelText(/search/i), "ada");
    await waitFor(() => expect(seen).toContain("ada"));
  });

  it("shows an error state on 500", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json({}, { status: 500 })));
    setup();
    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("respects ?view=list on initial render", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup("/enquiries?view=list");
    expect(await screen.findByText("E-AAA-001")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-column-new")).not.toBeInTheDocument();
  });

  it("kanban toggle remains reachable when a status filter is active", async () => {
    // Landing from the dashboard "New enquiries" KPI puts ?status=new in the
    // URL, which flips the implicit default to "list". The user must still be
    // able to switch back to the Kanban view.
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup("/enquiries?status=new");
    expect(await screen.findByText("E-AAA-001")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-column-new")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /kanban/i }));
    expect(await screen.findByTestId("kanban-column-new")).toBeInTheDocument();
  });
});
