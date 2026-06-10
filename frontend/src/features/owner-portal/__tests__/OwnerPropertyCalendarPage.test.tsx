import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { OwnerPropertyCalendarPage } from "../OwnerPropertyCalendarPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const PROPERTY = {
  id: 3,
  name: "Villa Anemoi",
  display_name: "Villa Anemoi",
  slug: "villa-anemoi",
  status: "active",
  category: 1,
  group: 1,
  region: 1,
  guests: 8,
  bedrooms: 4,
  hero_image_url: null,
  can_request_block: true,
};

function blockRequest(overrides: Record<string, unknown> = {}) {
  return {
    id: 50,
    property: 3,
    date_from: "2026-08-01",
    date_to: "2026-08-08",
    kind: "owner_stay",
    notes: "",
    status: "approved",
    created_at: "2026-06-03T10:00:00Z",
    ...overrides,
  };
}

function mockEndpoints(opts: { canRequestBlock?: boolean; requests?: unknown[] } = {}) {
  const property = { ...PROPERTY, can_request_block: opts.canRequestBlock ?? true };
  server.use(
    http.get("/api/v1/owner/properties/3", () => HttpResponse.json(property)),
    http.get("/api/v1/owner/properties/3/calendar", () =>
      HttpResponse.json({
        property_id: 3,
        can_request_block: opts.canRequestBlock ?? true,
        cells: [],
      }),
    ),
    http.get("/api/v1/owner/block-requests", () => HttpResponse.json(opts.requests ?? [])),
  );
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/owner/properties/:id/calendar" element={<OwnerPropertyCalendarPage />} />
    </Routes>,
    { route: "/owner/properties/3/calendar" },
  );
}

afterEach(() => server.resetHandlers());

describe("OwnerPropertyCalendarPage block requests", () => {
  it("shows the Block dates button when can_request_block is true", async () => {
    mockEndpoints({ canRequestBlock: true });
    renderPage();
    expect(await screen.findByRole("button", { name: /block dates/i })).toBeInTheDocument();
  });

  it("hides the Block dates button when can_request_block is false", async () => {
    mockEndpoints({ canRequestBlock: false });
    renderPage();
    // The calendar settles (back button present) before we assert the absence.
    await screen.findByRole("button", { name: /back to properties/i });
    expect(screen.queryByRole("button", { name: /block dates/i })).not.toBeInTheDocument();
  });

  it("lists existing requests and cancels one", async () => {
    let cancelled = false;
    mockEndpoints({ requests: [blockRequest()] });
    server.use(
      http.post("/api/v1/owner/block-requests/50:cancel", () => {
        cancelled = true;
        return HttpResponse.json(blockRequest({ status: "cancelled" }));
      }),
    );
    renderPage();

    // Inclusive nights: [1 Aug, 8 Aug) is 7 nights ending the 7th — never "8 Aug".
    expect(await screen.findByText("1–7 Aug 2026 · 7 nights")).toBeInTheDocument();
    expect(screen.queryByText(/8 Aug/)).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: /^remove$/i }));
    await waitFor(() => expect(cancelled).toBe(true));
  });

  it("renders a lone booking checkout as an AM/PM half-day turnover cell", async () => {
    // A current-month day so it lands inside the visible (in-month) grid.
    const now = new Date();
    const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-15`;
    mockEndpoints();
    server.use(
      http.get("/api/v1/owner/properties/3/calendar", () =>
        HttpResponse.json({
          property_id: 3,
          can_request_block: true,
          cells: [
            {
              date: iso,
              available: true,
              reason: null,
              segments: {
                am: { available: false, reason: "booked" },
                pm: { available: true, reason: null },
              },
            },
          ],
        }),
      ),
    );
    renderPage();
    expect(
      await screen.findByLabelText(/morning Booked, afternoon Available/i),
    ).toBeInTheDocument();
  });

  it("shows booked state on adjacent-month days in the grid", async () => {
    // May 2026 starts on a Friday, so the grid leads with 27–30 April.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 4, 15));
    try {
      mockEndpoints();
      server.use(
        http.get("/api/v1/owner/properties/3/calendar", () =>
          HttpResponse.json({
            property_id: 3,
            can_request_block: true,
            cells: [{ date: "2026-04-28", available: false, reason: "booked" }],
          }),
        ),
      );
      renderPage();
      expect(await screen.findByLabelText(/28 April: Booked/i)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders a single-night block without a date range", async () => {
    mockEndpoints({
      requests: [blockRequest({ date_from: "2026-08-01", date_to: "2026-08-02" })],
    });
    renderPage();
    expect(await screen.findByText("1 Aug 2026 · 1 night")).toBeInTheDocument();
  });
});
