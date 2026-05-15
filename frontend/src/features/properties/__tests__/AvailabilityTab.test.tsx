import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { AvailabilityTab } from "../tabs/AvailabilityTab";

const propertyFixture = {
  id: 5,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

interface Cell {
  date: string;
  available: boolean;
  reason: string;
  block_id?: number | null;
  segments?: {
    am: { available: boolean; reason: string; block_id?: number | null };
    pm: { available: boolean; reason: string; block_id?: number | null };
  };
}

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)));
}

function installCalendar(cells: Cell[]) {
  server.use(
    http.get("/api/v1/properties/5/availability", () =>
      HttpResponse.json({ property_id: 5, cells }),
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
  useAuthStore.getState().clear();
});

describe("AvailabilityTab", () => {
  it("renders current month with weekday headers", async () => {
    installBaseHandlers();
    installCalendar([]);
    setup();

    expect(await screen.findByText("May 2026")).toBeInTheDocument();
    for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
      expect(screen.getByText(day)).toBeInTheDocument();
    }
  });

  it("renders a booked cell that links to the booking", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/availability", () =>
        HttpResponse.json({
          property_id: 5,
          cells: [
            { date: "2026-05-10", available: false, reason: "booked", block_id: null },
            { date: "2026-05-11", available: false, reason: "booked", block_id: null },
            { date: "2026-05-12", available: false, reason: "booked", block_id: null },
          ],
        }),
      ),
      http.get("/api/v1/bookings", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 42,
              reference: "BK-042",
              status: "confirmed",
              date_from: "2026-05-10",
              date_to: "2026-05-13",
              guest_name: "Jane Doe",
            },
          ]),
        ),
      ),
      http.get("/api/v1/availability", () => HttpResponse.json({ records: [] })),
    );

    setup();

    const cell10 = await screen.findByRole("link", { name: "10" });
    expect(cell10).toHaveAttribute("href", "/bookings/42");
    expect(screen.getByRole("link", { name: "12" })).toHaveAttribute("href", "/bookings/42");
    expect(screen.queryByRole("link", { name: "13" })).not.toBeInTheDocument();
  });

  it("renders an owner block cell with its reason label", async () => {
    installBaseHandlers();
    installCalendar([
      { date: "2026-05-20", available: false, reason: "owner_block", block_id: 1 },
      { date: "2026-05-21", available: false, reason: "owner_block", block_id: 1 },
    ]);

    setup();

    expect(await screen.findByLabelText(/20 May: Owner block/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/21 May: Owner block/i)).toBeInTheDocument();
  });

  it("renders a split changeover cell with am/pm aria-label", async () => {
    installBaseHandlers();
    installCalendar([
      {
        date: "2026-05-15",
        available: false,
        reason: "booked",
        block_id: null,
        segments: {
          am: { available: false, reason: "booked", block_id: null },
          pm: { available: false, reason: "owner_block", block_id: 3 },
        },
      },
    ]);

    setup();

    expect(
      await screen.findByLabelText(/15 May: morning Booked, afternoon Owner block/i),
    ).toBeInTheDocument();
  });

  it("disables Add block without the reservations role", async () => {
    installBaseHandlers();
    installCalendar([]);
    setup();

    const btn = await screen.findByRole("button", { name: /Add block/i });
    expect(btn).toBeDisabled();
  });

  it("enables Add block and opens the dialog with the reservations role", async () => {
    setReservationsUser();
    installBaseHandlers();
    installCalendar([]);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setup();

    const btn = await screen.findByRole("button", { name: /Add block/i });
    expect(btn).toBeEnabled();
    await user.click(btn);
    expect(await screen.findByText(/Add availability block/i)).toBeInTheDocument();
  });

  it("navigates between months", async () => {
    installBaseHandlers();
    installCalendar([]);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setup();

    expect(await screen.findByText("May 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next month/i }));
    await waitFor(() => expect(screen.getByText("June 2026")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /Previous month/i }));
    await waitFor(() => expect(screen.getByText("May 2026")).toBeInTheDocument());
  });

  it("renders error state when the calendar endpoint fails", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/availability", () => HttpResponse.json({}, { status: 500 })),
      http.get("/api/v1/bookings", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/availability", () => HttpResponse.json({ records: [] })),
    );

    setup();

    expect(await screen.findByText(/Couldn't load availability/i)).toBeInTheDocument();
  });
});
