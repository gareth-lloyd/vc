import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { AvailabilityTab } from "../tabs/AvailabilityTab";
import type { PropertyDetail } from "../schemas";

function makeFixture(overrides: Partial<PropertyDetail> = {}) {
  return {
    id: 5,
    name: "Casa Norte",
    display_name: "Casa Norte",
    slug: "casa-norte",
    status: "active",
    channel: "direct",
    has_active_ical_feed: false,
    feature_ids: [],
    availability_owner_updated_at: null,
    availability_confirmed_at: null,
    availability_confirmed_by_name: null,
    calendar_last_imported_at: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function installHandlers(fixture: ReturnType<typeof makeFixture>) {
  server.use(
    http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(fixture)),
    http.get("/api/v1/properties/5/availability", () =>
      HttpResponse.json({ property_id: 5, cells: [] }),
    ),
    http.get("/api/v1/bookings", () => HttpResponse.json(drfPage([]))),
    http.get("/api/v1/availability", () => HttpResponse.json({ records: [] })),
  );
}

function setReservationsUser() {
  useAuthStore.getState().setMe(
    {
      id: 1,
      email: "a@test.com",
      first_name: "A",
      last_name: "T",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      preferred_language: "en",
      role: "RESERVATIONS",
    },
    { role: "RESERVATIONS", is_superuser: false, permissions: [] },
  );
}

function setViewerUser() {
  useAuthStore.getState().setMe(
    {
      id: 2,
      email: "v@test.com",
      first_name: "V",
      last_name: "T",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      preferred_language: "en",
      role: "VIEWER",
    },
    { role: "VIEWER", is_superuser: false, permissions: [] },
  );
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="availability" replace />} />
        <Route path="availability" element={<AvailabilityTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-norte/availability" },
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 4, 15));
});

afterEach(() => {
  vi.useRealTimers();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  useAuthStore.getState().clear();
});

describe("AvailabilityTab freshness signals", () => {
  it("shows the owner-updated and confirmed lines; hides the import line without a feed", async () => {
    setReservationsUser();
    installHandlers(
      makeFixture({
        availability_owner_updated_at: "2026-05-10T00:00:00Z",
        availability_confirmed_at: "2026-05-12T00:00:00Z",
        availability_confirmed_by_name: "Sam Staffer",
      }),
    );
    setup();

    expect(await screen.findByText("Updated by owner")).toBeInTheDocument();
    expect(screen.getByText("Confirmed by VC staff")).toBeInTheDocument();
    expect(screen.getByText(/Sam Staffer/)).toBeInTheDocument();
    // No active feed → the calendar-import line is absent.
    expect(screen.queryByText("Calendar imported")).not.toBeInTheDocument();
  });

  it("shows the calendar-import line for a villa with an active feed", async () => {
    setReservationsUser();
    installHandlers(
      makeFixture({
        has_active_ical_feed: true,
        calendar_last_imported_at: "2026-05-14T00:00:00Z",
      }),
    );
    setup();

    expect(await screen.findByText("Calendar imported")).toBeInTheDocument();
  });

  it("shows 'Not yet confirmed' until a staffer confirms", async () => {
    setReservationsUser();
    installHandlers(makeFixture());
    setup();

    expect(await screen.findByText("Not yet confirmed")).toBeInTheDocument();
  });

  it("confirms availability and toasts success", async () => {
    setReservationsUser();
    installHandlers(makeFixture());
    let posted = false;
    server.use(
      http.post("/api/v1/properties/5:confirm-availability", () => {
        posted = true;
        return HttpResponse.json(
          makeFixture({
            availability_confirmed_at: "2026-05-15T00:00:00Z",
            availability_confirmed_by_name: "Sam Staffer",
          }),
        );
      }),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setup();

    const btn = await screen.findByRole("button", { name: /Mark as up-to-date/i });
    expect(btn).toBeEnabled();
    await user.click(btn);

    await waitFor(() => expect(posted).toBe(true));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("disables the confirm button for a read-only viewer", async () => {
    setViewerUser();
    installHandlers(makeFixture());
    setup();

    const btn = await screen.findByRole("button", { name: /Mark as up-to-date/i });
    expect(btn).toBeDisabled();
  });
});
