import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { ConciergeOverviewPage } from "../ConciergeOverviewPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const OVERVIEW = "/api/v1/concierge/overview";

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 100,
    reference: "B-CON-100",
    status: "deposit_paid",
    guest_name: "Ada Lovelace",
    property_name: "Casa Norte",
    region: "Mykonos",
    date_from: "2026-07-01",
    arrival_in_days: 5,
    services: { chef: "not_started", car: "done" },
    progress: 40,
    manager: "Wri Ter",
    tier: "signature",
    ...overrides,
  };
}

const baseUser = {
  id: 1,
  email: "writer@example.com",
  first_name: "Wri",
  last_name: "Ter",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  preferred_language: "en",
};

function grantWriterRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: "RESERVATIONS" },
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function clearRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: null },
    role: null,
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function setup() {
  return renderWithProviders(<ConciergeOverviewPage />, { route: "/concierge" });
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
  clearRole();
});

describe("ConciergeOverviewPage", () => {
  it("renders a matrix row from the API", async () => {
    grantWriterRole();
    server.use(http.get(OVERVIEW, () => HttpResponse.json([row()])));
    setup();
    expect(await screen.findByText("B-CON-100")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Casa Norte")).toBeInTheDocument();
    expect(screen.getByText("Mykonos")).toBeInTheDocument();
    // Countdown pill + progress.
    expect(screen.getByText(/in 5 days/i)).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("labels an in-residence booking as in-house, not departed", async () => {
    grantWriterRole();
    server.use(http.get(OVERVIEW, () => HttpResponse.json([row({ arrival_in_days: -2 })])));
    setup();
    await screen.findByText("B-CON-100");
    expect(screen.getByText(/in residence/i)).toBeInTheDocument();
    expect(screen.queryByText(/departed/i)).not.toBeInTheDocument();
  });

  it("renders the legend of all six statuses", async () => {
    grantWriterRole();
    server.use(http.get(OVERVIEW, () => HttpResponse.json([row()])));
    setup();
    await screen.findByText("B-CON-100");
    expect(screen.getByText("Service status")).toBeInTheDocument();
    for (const label of [
      "Not started",
      "Working on it",
      "Waiting",
      "Arranged independently",
      "Not required",
      "Done",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("shows an empty state when there are no live bookings", async () => {
    grantWriterRole();
    server.use(http.get(OVERVIEW, () => HttpResponse.json([])));
    setup();
    expect(await screen.findByText(/no live bookings/i)).toBeInTheDocument();
  });

  it("renders cells read-only (no status trigger) without the reservations role", async () => {
    clearRole();
    server.use(http.get(OVERVIEW, () => HttpResponse.json([row()])));
    setup();
    await screen.findByText("B-CON-100");
    expect(screen.queryByRole("button", { name: /set chef status/i })).not.toBeInTheDocument();
  });

  it("sets a service status via the cell popover", async () => {
    grantWriterRole();
    let posted: unknown = null;
    server.use(
      http.get(OVERVIEW, () => HttpResponse.json([row()])),
      http.post(`/api/v1/concierge/100/coverage/chef:set-status`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({
          id: 1,
          booking: 100,
          service: "chef",
          status: "done",
          notes: "",
        });
      }),
    );
    setup();
    await screen.findByText("B-CON-100");
    await userEvent.click(screen.getByRole("button", { name: /set chef status for B-CON-100/i }));
    const popover = await screen.findByRole("dialog");
    await userEvent.click(within(popover).getByRole("button", { name: /done/i }));
    await waitFor(() => expect(posted).toEqual({ status: "done" }));
    expect(toast.success).toHaveBeenCalled();
  });

  it("toasts on a failed set-status", async () => {
    grantWriterRole();
    server.use(
      http.get(OVERVIEW, () => HttpResponse.json([row()])),
      http.post(`/api/v1/concierge/100/coverage/chef:set-status`, () =>
        HttpResponse.json({ detail: "Boom" }, { status: 500 }),
      ),
    );
    setup();
    await screen.findByText("B-CON-100");
    await userEvent.click(screen.getByRole("button", { name: /set chef status for B-CON-100/i }));
    const popover = await screen.findByRole("dialog");
    await userEvent.click(within(popover).getByRole("button", { name: /done/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
