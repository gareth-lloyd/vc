import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
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

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)));
}

function installEmptyAvailability() {
  server.use(
    http.get("/api/v1/availability", () => HttpResponse.json({ records: [] })),
    http.get("/api/v1/bookings", () => HttpResponse.json(drfPage([]))),
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
});

describe("AvailabilityTab", () => {
  it("renders current month by default with weekday headers", async () => {
    installBaseHandlers();
    installEmptyAvailability();
    setup();

    expect(await screen.findByText("May 2026")).toBeInTheDocument();
    for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
      expect(screen.getByText(day)).toBeInTheDocument();
    }
  });

  it("renders a booked cell that links to the booking", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/availability", () => HttpResponse.json({ records: [] })),
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
    );

    setup();

    const cell10 = await screen.findByRole("link", { name: "10" });
    expect(cell10).toHaveAttribute("href", "/bookings/42");

    const cell12 = screen.getByRole("link", { name: "12" });
    expect(cell12).toHaveAttribute("href", "/bookings/42");

    expect(screen.queryByRole("link", { name: "13" })).not.toBeInTheDocument();
  });

  it("renders held cells with reason labels", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/availability", () =>
        HttpResponse.json({
          records: [
            {
              id: 1,
              property: 5,
              date_from: "2026-05-20",
              date_to: "2026-05-22",
              expires_at: null,
              released_at: null,
              reason: "owner_block",
              created_at: "2026-05-01T00:00:00Z",
            },
          ],
        }),
      ),
      http.get("/api/v1/bookings", () => HttpResponse.json(drfPage([]))),
    );

    setup();

    const held = await screen.findByLabelText(/20 May: Owner block/i);
    expect(held).toBeInTheDocument();
    const held21 = screen.getByLabelText(/21 May: Owner block/i);
    expect(held21).toBeInTheDocument();
  });

  it("booking takes precedence over hold on the same day", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/availability", () =>
        HttpResponse.json({
          records: [
            {
              id: 1,
              property: 5,
              date_from: "2026-05-10",
              date_to: "2026-05-14",
              expires_at: null,
              released_at: null,
              reason: "manual",
              created_at: "2026-05-01T00:00:00Z",
            },
          ],
        }),
      ),
      http.get("/api/v1/bookings", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 99,
              reference: "BK-099",
              status: "confirmed",
              date_from: "2026-05-11",
              date_to: "2026-05-13",
              guest_name: "Overlap Guest",
            },
          ]),
        ),
      ),
    );

    setup();

    const bookedCell = await screen.findByRole("link", { name: "12" });
    expect(bookedCell).toHaveAttribute("href", "/bookings/99");

    expect(screen.queryByLabelText(/12 May: Manual hold/i)).not.toBeInTheDocument();
  });

  it("navigates between months", async () => {
    installBaseHandlers();
    installEmptyAvailability();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setup();

    expect(await screen.findByText("May 2026")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Next month/i }));
    await waitFor(() => expect(screen.getByText("June 2026")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Previous month/i }));
    await waitFor(() => expect(screen.getByText("May 2026")).toBeInTheDocument());
  });

  it("renders error state when an endpoint fails", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/availability", () => HttpResponse.json({}, { status: 500 })),
      http.get("/api/v1/bookings", () => HttpResponse.json(drfPage([]))),
    );

    setup();

    expect(await screen.findByText(/Couldn't load availability/i)).toBeInTheDocument();
  });
});
