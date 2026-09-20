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

const STATUS_COUNTS = { new: 236, progressing: 9, quote_sent: 498, converted: 12 };

function mockStatusCounts(counts: Record<string, number> = STATUS_COUNTS) {
  server.use(http.get("/api/v1/enquiries/status-counts", () => HttpResponse.json(counts)));
}

/**
 * The board fans out one request per KANBAN_STATUSES entry. Answer each with
 * only the rows of that status, the way the API does, and record what was
 * asked for.
 */
function mockKanbanFanOut(rows = listFixture.results, counts = STATUS_COUNTS) {
  const seen: { status: string | null; page_size: string | null }[] = [];
  mockStatusCounts(counts);
  server.use(
    http.get("/api/v1/enquiries", ({ request }) => {
      const params = new URL(request.url).searchParams;
      const status = params.get("status");
      seen.push({ status, page_size: params.get("page_size") });
      const results = rows.filter((r) => r.status === status);
      return HttpResponse.json({
        count: counts[status as keyof typeof counts] ?? results.length,
        next: null,
        previous: null,
        results,
      });
    }),
  );
  return seen;
}

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
    mockKanbanFanOut();
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
    mockStatusCounts();
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

  it("fetches one bounded page per column instead of one unfiltered page", async () => {
    // GAP-118: the board used to take the first page of ALL enquiries and
    // bucket it, so a column past the page boundary showed nothing. Each column
    // now asks for its own status with its own small page size, and no
    // unfiltered board request fires.
    const seen = mockKanbanFanOut();
    setup();

    await screen.findByTestId("kanban-column-new");
    await waitFor(() => expect(seen.length).toBe(3));
    expect(seen.map((r) => r.status).sort()).toEqual(["converted", "new", "quote_sent"]);
    expect(seen.every((r) => r.page_size === "20")).toBe(true);
  });

  it("ignores a ?status= left over from the list view when fanning out", async () => {
    // A dashboard deep-link leaves ?status=new in the URL. Each column supplies
    // its OWN status, so the stale one must not narrow the whole board.
    const seen = mockKanbanFanOut();
    setup("/enquiries?status=new&view=kanban");

    await screen.findByTestId("kanban-column-new");
    await waitFor(() => expect(seen.length).toBe(3));
    expect(
      within(screen.getByTestId("kanban-column-quote_sent")).getByText("Linus Torvalds"),
    ).toBeInTheDocument();
  });

  it("drops a page left over from the list view so no column is windowed", async () => {
    // The list view's pagination writes `page`/`page_size` to the URL. Each
    // column is its own first page, so a leftover `page=3` must not empty them.
    let seenPage: string | null = "unset";
    mockStatusCounts();
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        seenPage = new URL(request.url).searchParams.get("page");
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    setup("/enquiries?view=kanban&page=3&page_size=25");

    await screen.findByTestId("kanban-column-new");
    await waitFor(() => expect(seenPage).toBeNull());
  });

  it("badges each column from status-counts and footers the windowed remainder", async () => {
    // The ticket's headline defect: the board showed New 19 / Quote sent 7 from
    // `items.length` where status-counts says 236 / 498.
    mockKanbanFanOut();
    setup();

    const newCol = await screen.findByTestId("kanban-column-new");
    expect(within(newCol).getByText("236")).toBeInTheDocument();
    expect(within(newCol).getByText(/showing 1 of 236/i)).toBeInTheDocument();
    const quoted = screen.getByTestId("kanban-column-quote_sent");
    expect(within(quoted).getByText("498")).toBeInTheDocument();
    // "View all" drops into the list view filtered to that column.
    const viewAll = within(quoted).getByRole("link", { name: /view all/i });
    expect(viewAll).toHaveAttribute("href", expect.stringContaining("status=quote_sent"));
    expect(viewAll).toHaveAttribute("href", expect.stringContaining("view=list"));
  });

  it("keeps the loaded columns when one column's request fails", async () => {
    // GAP-118 turned one board request into one per column. A transient 500 on
    // a single lane must not replace the whole triage surface.
    mockStatusCounts();
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        if (status === "converted") return new HttpResponse(null, { status: 500 });
        const results = listFixture.results.filter((r) => r.status === status);
        return HttpResponse.json({ count: results.length, next: null, previous: null, results });
      }),
    );
    setup();

    const newCol = await screen.findByTestId("kanban-column-new");
    expect(await within(newCol).findByText("Ada Lovelace")).toBeInTheDocument();
    // The failed lane says so, in place — the board itself is still there.
    const converted = screen.getByTestId("kanban-column-converted");
    expect(within(converted).getByText(/couldn't load this column/i)).toBeInTheDocument();
    expect(screen.queryByText(/couldn't load enquiries/i)).not.toBeInTheDocument();
  });

  it("retries every column from the board-wide error state", async () => {
    // Only when NO column loads does the board surrender to the shared
    // ErrorState — and its retry has to reach all three requests.
    let attempts = 0;
    mockStatusCounts();
    server.use(
      http.get("/api/v1/enquiries", () => {
        attempts += 1;
        return new HttpResponse(null, { status: 503 });
      }),
    );
    setup();

    // `error instanceof ApiError` still narrows through the combined result.
    expect(await screen.findByText(/couldn't load enquiries \(503\)/i)).toBeInTheDocument();
    await waitFor(() => expect(attempts).toBe(3));

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(attempts).toBe(6));
  });

  it("labels each View all link with its column", async () => {
    // Three links reading only "View all" are indistinguishable in a screen
    // reader's link list.
    mockKanbanFanOut();
    setup();

    await screen.findByTestId("kanban-column-new");
    expect(
      await screen.findByRole("link", { name: /view all new enquiries/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /view all quote sent enquiries/i }),
    ).toBeInTheDocument();
  });

  it("shows no footer on a column that holds everything it counts", async () => {
    mockKanbanFanOut(listFixture.results, {
      new: 1,
      progressing: 0,
      quote_sent: 1,
      converted: 0,
    });
    setup();

    const newCol = await screen.findByTestId("kanban-column-new");
    await waitFor(() => expect(within(newCol).getByText("Ada Lovelace")).toBeInTheDocument());
    expect(within(newCol).queryByText(/showing/i)).not.toBeInTheDocument();
  });

  it("kanban toggle remains reachable when a status filter is active", async () => {
    // Landing from the dashboard "New enquiries" KPI puts ?status=new in the
    // URL, which flips the implicit default to "list". The user must still be
    // able to switch back to the Kanban view.
    // MSW prepends runtime handlers, so no blanket `/enquiries` handler here —
    // it would shadow the fan-out and this test would assert nothing about the
    // board it toggles to.
    mockKanbanFanOut();
    setup("/enquiries?status=new");
    expect(await screen.findByText("E-AAA-001")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-column-new")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /kanban/i }));
    expect(await screen.findByTestId("kanban-column-new")).toBeInTheDocument();
  });

  it("opens the unified workspace (/enquiries/:id) on a Kanban card click", async () => {
    mockKanbanFanOut();
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

  it("excludes Dead and Converted from the stage tabs", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(listFixture)));
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    expect(screen.getByRole("tab", { name: /new/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /dead/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /converted/i })).not.toBeInTheDocument();
  });

  it("forwards the lead_status filter to the API", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("lead_status"));
        return HttpResponse.json(listFixture);
      }),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    await userEvent.click(screen.getByRole("combobox", { name: /filter by lead status/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Hot" }));

    await waitFor(() => expect(seen).toContain("hot"));
  });

  it("forwards the salesperson 'unassigned' filter to the API", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/v1/users", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
      http.get("/api/v1/enquiries", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("assigned_to"));
        return HttpResponse.json(listFixture);
      }),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    await userEvent.click(screen.getByRole("combobox", { name: /filter by sales person/i }));
    await userEvent.click(await screen.findByRole("option", { name: /unassigned/i }));

    await waitFor(() => expect(seen).toContain("unassigned"));
  });

  it("forwards the page_size selection to the API", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/v1/enquiries", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("page_size"));
        return HttpResponse.json(listFixture);
      }),
    );
    setup("/enquiries?view=list");

    await screen.findByText("E-AAA-001");
    await userEvent.click(screen.getByRole("combobox", { name: /rows per page/i }));
    await userEvent.click(await screen.findByRole("option", { name: "100 / page" }));

    await waitFor(() => expect(seen).toContain("100"));
  });
});
