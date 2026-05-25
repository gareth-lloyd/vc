import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { OverviewTab } from "../tabs/OverviewTab";
import { TimelineTab } from "../tabs/TimelineTab";

const bookingFixture = {
  id: 51,
  reference: "B-AAA-001",
  status: "deposit_paid",
  property: 12,
  guest: 99,
  agent: null,
  assigned_to: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 1,
  currency: 1,
  rental_price: "1500.00",
  balance_due: "1000.00",
  balance_due_at: "2026-06-01",
  site_source: "main_website",
  is_archived: false,
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  property_name: "Casa Norte",
  guest_name: "Ada Lovelace",
  guest_email: "ada@example.com",
  currency_code: "GBP",
  total: "2500.00",
  night_count: 7,
  pricing_snapshot: {},
  discount: "0.00",
  adjustment: "0.00",
  terms_version: 1,
  terms_accepted_at: "2026-05-01T00:00:00Z",
  payment_method: "card",
  cancel_reason: "",
  cancelled_at: null,
};

const activityFixture = [
  {
    id: 1,
    booking: 51,
    from_status: null,
    to_status: "draft",
    actor: null,
    source: "system",
    reason: "",
    meta: {},
    created_at: "2026-05-01T00:00:00Z",
  },
  {
    id: 2,
    booking: 51,
    from_status: "awaiting_deposit",
    to_status: "deposit_paid",
    actor: 1,
    source: "webhook",
    reason: "Stripe charge succeeded",
    meta: { payment_id: 42 },
    created_at: "2026-05-02T00:00:00Z",
  },
];

function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<OverviewTab />} />
        <Route path="timeline" element={<TimelineTab />} />
        <Route path="finance" element={<ComingSoonTab tabName="Finance" />} />
      </Route>
    </Routes>,
    { route: initial },
  );
}

describe("BookingDetailLayout", () => {
  it("renders right rail with reference, status, dates, financials", async () => {
    server.use(http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)));
    setup("/bookings/51/overview");
    await waitFor(() => expect(screen.getAllByText("B-AAA-001").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Casa Norte").length).toBeGreaterThan(0);
    expect(screen.getAllByText("deposit_paid").length).toBeGreaterThan(0);
    expect(screen.getAllByText("£2,500.00").length).toBeGreaterThan(0);
  });

  it("renders Overview content for the guest + property", async () => {
    server.use(http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)));
    setup("/bookings/51/overview");
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText(/2 adults, 1 child/i)).toBeInTheDocument();
  });

  it("renders the Timeline tab when navigated to", async () => {
    server.use(
      http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)),
      http.get("/api/v1/bookings/51/activity", () => HttpResponse.json(activityFixture)),
    );
    setup("/bookings/51/timeline");
    expect(await screen.findByText("awaiting_deposit → deposit_paid")).toBeInTheDocument();
    expect(screen.getByText(/Stripe charge succeeded/i)).toBeInTheDocument();
  });

  it("does NOT call activity endpoint when on ComingSoon Finance tab", async () => {
    let activityCalls = 0;
    server.use(
      http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)),
      http.get("/api/v1/bookings/51/activity", () => {
        activityCalls += 1;
        return HttpResponse.json(activityFixture);
      }),
    );
    setup("/bookings/51/finance");
    expect(await screen.findByText(/Finance — coming in next phase/i)).toBeInTheDocument();
    expect(activityCalls).toBe(0);
  });

  it("falls back to placeholders when name fields are missing", async () => {
    const noNames = {
      ...bookingFixture,
      property_name: null,
      guest_name: null,
      guest_email: null,
    };
    server.use(http.get("/api/v1/bookings/51", () => HttpResponse.json(noNames)));
    setup("/bookings/51/overview");
    await waitFor(() => expect(screen.getAllByText(/Guest #99/i).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Property #12/i).length).toBeGreaterThan(0);
  });

  it("renders error state and recovers on retry", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/bookings/51", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(bookingFixture);
      }),
    );
    setup("/bookings/51/overview");
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
  });
});

describe("TimelineTab error/empty", () => {
  it("renders an empty state when no activity", async () => {
    server.use(
      http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)),
      http.get("/api/v1/bookings/51/activity", () => HttpResponse.json([])),
    );
    setup("/bookings/51/timeline");
    expect(await screen.findByText(/no activity yet/i)).toBeInTheDocument();
  });

  it("renders an error state on activity 500", async () => {
    server.use(
      http.get("/api/v1/bookings/51", () => HttpResponse.json(bookingFixture)),
      http.get("/api/v1/bookings/51/activity", () => HttpResponse.json({}, { status: 500 })),
    );
    setup("/bookings/51/timeline");
    expect(await screen.findByText(/Couldn't load activity/i)).toBeInTheDocument();
  });
});
