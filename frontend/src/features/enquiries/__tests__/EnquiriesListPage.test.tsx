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
      status: "progressing" as const,
      first_name: "Grace",
      last_name: "Hopper",
      email: "grace@example.com",
    },
    {
      ...baseEnquiry,
      id: 3,
      reference: "E-CCC-003",
      status: "quote_sent" as const,
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
      <Route path="/enquiries/:id" element={<div>Detail page</div>} />
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
    const quotedCol = screen.getByTestId("kanban-column-quote_sent");

    expect(within(newCol).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(quotedCol).getByText("Linus Torvalds")).toBeInTheDocument();
    // `progressing` has no forward affordance in the app, so the board omits that
    // column — a progressing (migrated) enquiry doesn't appear on the board.
    expect(screen.queryByTestId("kanban-column-progressing")).not.toBeInTheDocument();
    expect(screen.queryByText("Grace Hopper")).not.toBeInTheDocument();
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

  it("ignores ?status= in kanban view so no column is silently emptied", async () => {
    let seenStatus: string | null = "unset";
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        seenStatus = new URL(request.url).searchParams.get("status");
        return HttpResponse.json(listFixture);
      }),
    );
    setup("/enquiries?status=new&view=kanban");

    await screen.findByTestId("kanban-column-new");
    // The board query dropped the status filter…
    await waitFor(() => expect(seenStatus).toBeNull());
    // …so cards from other statuses still populate their columns.
    expect(
      within(screen.getByTestId("kanban-column-quote_sent")).getByText("Linus Torvalds"),
    ).toBeInTheDocument();
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

  it("opens the unified workspace (/enquiries/:id) on a Kanban card click", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup();
    await userEvent.click(await screen.findByText("Ada Lovelace"));
    expect(await screen.findByText("Detail page")).toBeInTheDocument();
  });

  it("opens the unified workspace (/enquiries/:id) on a list-view row click", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup("/enquiries?view=list");
    await userEvent.click(await screen.findByText("E-AAA-001"));
    expect(await screen.findByText("Detail page")).toBeInTheDocument();
  });

  it("renders the GAP-039 enrichment columns in list view", async () => {
    server.use(
      http.get("/api/v1/enquiries", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              ...baseEnquiry,
              region: 5,
              region_name: "Cyclades",
              assigned_to: 7,
              assigned_to_name: "Mona Sales",
              lead_status: "hot",
              is_flexible: false,
              flexibility_days: 2,
            },
          ],
        }),
      ),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    // New columns + their derived cell values all render.
    expect(screen.getByText("Region")).toBeInTheDocument();
    expect(screen.getByText("Cyclades")).toBeInTheDocument();
    expect(screen.getByText("Sales person")).toBeInTheDocument();
    expect(screen.getByText("Mona Sales")).toBeInTheDocument();
    expect(screen.getByText("Lead status")).toBeInTheDocument();
    expect(screen.getByText("Hot")).toBeInTheDocument();
    expect(screen.getByText("± 2 days")).toBeInTheDocument();
  });

  it("maps the Flex? column across specific / spread / open-ended", async () => {
    server.use(
      http.get("/api/v1/enquiries", () =>
        HttpResponse.json({
          count: 3,
          next: null,
          previous: null,
          results: [
            {
              ...baseEnquiry,
              id: 1,
              reference: "E-SPECIFIC",
              is_flexible: false,
              flexibility_days: 0,
            },
            {
              ...baseEnquiry,
              id: 2,
              reference: "E-SPREAD",
              is_flexible: true,
              flexibility_days: 3,
            },
            { ...baseEnquiry, id: 3, reference: "E-OPEN", is_flexible: true, flexibility_days: 0 },
          ],
        }),
      ),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-SPECIFIC");
    expect(screen.getByText("Specific dates")).toBeInTheDocument();
    expect(screen.getByText("± 3 days")).toBeInTheDocument();
    expect(screen.getByText("Flexible")).toBeInTheDocument();
  });

  it("falls back to — for region and 'Unassigned' for an unowned enquiry", async () => {
    server.use(
      http.get("/api/v1/enquiries", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [{ ...baseEnquiry, region: null, assigned_to: null }],
        }),
      ),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });
});
