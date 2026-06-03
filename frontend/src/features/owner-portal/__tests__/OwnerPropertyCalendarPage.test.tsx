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
    status: "pending",
    review_note: "",
    reviewed_at: null,
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
  it("shows the Request block button when can_request_block is true", async () => {
    mockEndpoints({ canRequestBlock: true });
    renderPage();
    expect(await screen.findByRole("button", { name: /request block/i })).toBeInTheDocument();
  });

  it("hides the Request block button when can_request_block is false", async () => {
    mockEndpoints({ canRequestBlock: false });
    renderPage();
    // The calendar settles (back button present) before we assert the absence.
    await screen.findByRole("button", { name: /back to properties/i });
    expect(screen.queryByRole("button", { name: /request block/i })).not.toBeInTheDocument();
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

    await userEvent.click(await screen.findByRole("button", { name: /^cancel$/i }));
    await waitFor(() => expect(cancelled).toBe(true));
  });
});
