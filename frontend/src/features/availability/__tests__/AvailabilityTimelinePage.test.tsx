import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { format, startOfWeek } from "date-fns";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { AvailabilityTimelinePage } from "../AvailabilityTimelinePage";

const villas = drfPage([
  { id: 1, name: "Casa Norte", slug: "casa-norte", status: "active" },
  { id: 2, name: "Villa Azul", slug: "villa-azul", status: "active" },
]);

// Window pinned via ?start=2026-06-08 so band dates are deterministic.
const START = "2026-06-08";

const bands = {
  records: [
    {
      id: 11,
      property: 1,
      date_from: "2026-06-10",
      date_to: "2026-06-15",
      expires_at: null,
      released_at: null,
      reason: "owner_block",
      notes: "Family stay",
      created_at: null,
    },
  ],
  bookings: [
    {
      id: 21,
      property: 2,
      date_from: "2026-06-12",
      date_to: "2026-06-19",
      status: "deposit_paid",
      reference: "VC1001",
      guest_name: "Ada Lovelace",
    },
  ],
};

function installTaxonomyHandlers() {
  server.use(
    http.get("/api/v1/regions", () =>
      HttpResponse.json(drfPage([{ id: 1, country: 1, name: "Ibiza", slug: "ibiza" }])),
    ),
    http.get("/api/v1/collections", () =>
      HttpResponse.json(drfPage([{ id: 1, name: "Signature", slug: "signature" }])),
    ),
  );
}

function renderPage(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/availability" element={<AvailabilityTimelinePage />} />
    </Routes>,
    { route },
  );
}

beforeEach(installTaxonomyHandlers);

describe("AvailabilityTimelinePage", () => {
  it("shows the filter gate and fires zero data requests without filters", async () => {
    let propertyCalls = 0;
    let availabilityCalls = 0;
    server.use(
      http.get("/api/v1/properties", () => {
        propertyCalls += 1;
        return HttpResponse.json(villas);
      }),
      http.get("/api/v1/availability", () => {
        availabilityCalls += 1;
        return HttpResponse.json(bands);
      }),
    );
    renderPage("/availability");
    expect(await screen.findByText(/filter to see availability/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(propertyCalls).toBe(0);
      expect(availabilityCalls).toBe(0);
    });
  });

  it("renders rows and bands once a filter is set, without date params on /properties", async () => {
    const propertyParams: URLSearchParams[] = [];
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        propertyParams.push(new URL(request.url).searchParams);
        return HttpResponse.json(villas);
      }),
      http.get("/api/v1/availability", () => HttpResponse.json(bands)),
    );
    renderPage(`/availability?country=es&start=${START}`);

    expect(await screen.findByText("Casa Norte")).toBeInTheDocument();
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /VC1001/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /owner block/i })).toBeInTheDocument();

    expect(propertyParams.length).toBeGreaterThan(0);
    for (const params of propertyParams) {
      expect(params.get("date_from")).toBeNull();
      expect(params.get("date_to")).toBeNull();
      expect(params.get("country")).toBe("es");
      expect(params.get("ordering")).toBe("name");
    }
  });

  it("opens a booking popover with guest, reference, status, and a booking link", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", () => HttpResponse.json(bands)),
    );
    renderPage(`/availability?country=es&start=${START}`);

    await userEvent.click(await screen.findByRole("button", { name: /VC1001/ }));
    const popover = await screen.findByRole("dialog");
    expect(popover).toHaveTextContent("Ada Lovelace");
    expect(popover).toHaveTextContent("VC1001");
    expect(popover).toHaveTextContent(/deposit paid/i);
    const link = screen.getByRole("link", { name: /open booking/i });
    expect(link).toHaveAttribute("href", "/bookings/21");
  });

  it("opens a hold popover with reason, notes, and a villa-calendar link", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", () => HttpResponse.json(bands)),
    );
    renderPage(`/availability?country=es&start=${START}`);

    await userEvent.click(await screen.findByRole("button", { name: /owner block/i }));
    const popover = await screen.findByRole("dialog");
    expect(popover).toHaveTextContent(/owner block/i);
    expect(popover).toHaveTextContent("Family stay");
    const link = screen.getByRole("link", { name: /open villa calendar/i });
    expect(link).toHaveAttribute("href", "/properties/casa-norte/availability");
  });

  it("links each villa name to its single-villa calendar", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", () => HttpResponse.json(bands)),
    );
    renderPage(`/availability?country=es&start=${START}`);

    const link = await screen.findByRole("link", { name: "Casa Norte" });
    expect(link).toHaveAttribute("href", "/properties/casa-norte/availability");
  });

  it("shows a refine notice and pager when more villas match than one page", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(drfPage(villas.results, { count: 120, next: "next-page" })),
      ),
      http.get("/api/v1/availability", () => HttpResponse.json(bands)),
    );
    renderPage(`/availability?country=es&start=${START}`);

    expect(await screen.findByText(/refine your filters/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next page/i })).toBeInTheDocument();
  });

  it("pages the window with prev/next/today", async () => {
    const windows: string[] = [];
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", ({ request }) => {
        windows.push(new URL(request.url).searchParams.get("from") ?? "");
        return HttpResponse.json(bands);
      }),
    );
    renderPage(`/availability?country=es&start=${START}`);
    await screen.findByText("Casa Norte");

    await userEvent.click(screen.getByRole("button", { name: /next week/i }));
    await waitFor(() => expect(windows).toContain("2026-06-15"));

    await userEvent.click(screen.getByRole("button", { name: /previous week/i }));
    await waitFor(() => expect(windows).toContain("2026-06-08"));

    await userEvent.click(screen.getByRole("button", { name: /^today$/i }));
    const currentMonday = format(startOfWeek(new Date(), { weekStartsOn: 1 }), "yyyy-MM-dd");
    await waitFor(() => expect(windows).toContain(currentMonday));
  });

  it("shows an error state with retry when availability fails", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(bands);
      }),
    );
    renderPage(`/availability?country=es&start=${START}`);

    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByRole("button", { name: /VC1001/ })).toBeInTheDocument();
  });

  it("stacks overlapping bookings into separate sub-lanes, both clickable", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(villas)),
      http.get("/api/v1/availability", () =>
        HttpResponse.json({
          records: [],
          bookings: [
            {
              id: 31,
              property: 1,
              date_from: "2026-06-10",
              date_to: "2026-06-17",
              status: "draft",
              reference: "VC2001",
              guest_name: "First Guest",
            },
            {
              id: 32,
              property: 1,
              date_from: "2026-06-12",
              date_to: "2026-06-20",
              status: "draft",
              reference: "VC2002",
              guest_name: "Second Guest",
            },
          ],
        }),
      ),
    );
    renderPage(`/availability?country=es&start=${START}`);

    const first = await screen.findByRole("button", { name: /VC2001/ });
    const second = screen.getByRole("button", { name: /VC2002/ });
    expect(first.style.top).not.toBe(second.style.top);
    await userEvent.click(second);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Second Guest");
  });
});
