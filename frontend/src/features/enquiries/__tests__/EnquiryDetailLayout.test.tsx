import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { EnquiryDetailLayout } from "../EnquiryDetailLayout";
import { DetailsTab } from "../tabs/DetailsTab";
import { ActivityTab } from "../tabs/ActivityTab";
import { NotesTab } from "../tabs/NotesTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const baseEnquiry = {
  id: 7,
  reference: "E-XYZ-007",
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
  children: 1,
  request_type: "quote" as const,
  assigned_to: null,
  agent: null,
  site_source: "main_website" as const,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  is_flexible: false,
  min_bedrooms: null,
  referral_code: "",
  inbound_message: "Hello, we'd like to enquire about Casa Norte.",
};

function makeUser(overrides: Partial<UserMe> = {}): UserMe {
  return {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    ...overrides,
  };
}

function asReservationsUser() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "RESERVATIONS",
    is_superuser: false,
    permissions: [],
  });
}

function asViewerUser() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "VIEWER",
    is_superuser: false,
    permissions: [],
  });
}

function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/enquiries/:id" element={<EnquiryDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<DetailsTab />} />
        <Route path="activity" element={<ActivityTab />} />
        <Route path="notes" element={<NotesTab />} />
      </Route>
    </Routes>,
    { route: initial },
  );
}

beforeEach(() => {
  useAuthStore.getState().clear();
});
afterEach(() => {
  server.resetHandlers();
});

describe("EnquiryDetailLayout", () => {
  it("renders the reference, status and guest name", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7/details");
    await waitFor(() => expect(screen.getAllByText("E-XYZ-007").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Ada Lovelace").length).toBeGreaterThan(0);
  });

  it("enables Close + Convert + Assign on a new enquiry, disables Reopen", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7/details");
    await screen.findByRole("button", { name: /assign/i });

    expect(screen.getByRole("button", { name: /assign/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /convert to quote/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /reopen/i })).toBeDisabled();
  });

  it("enables Reopen + disables Close/Convert when status is lost", async () => {
    asReservationsUser();
    server.use(
      http.get("/api/v1/enquiries/7", () => HttpResponse.json({ ...baseEnquiry, status: "lost" })),
    );
    setup("/enquiries/7/details");
    await screen.findByRole("button", { name: /reopen/i });

    expect(screen.getByRole("button", { name: /reopen/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /convert to quote/i })).toBeDisabled();
  });

  it("disables every action when the user lacks the reservations role", async () => {
    asViewerUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7/details");
    await screen.findByRole("button", { name: /assign/i });
    expect(screen.getByRole("button", { name: /assign/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeDisabled();
  });

  it("renders 'not found' (no retry) on 404", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json({}, { status: 404 })));
    setup("/enquiries/7/details");
    expect(await screen.findByText(/enquiry not found/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("renders an error with retry on 500", async () => {
    asReservationsUser();
    let calls = 0;
    server.use(
      http.get("/api/v1/enquiries/7", () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json(baseEnquiry);
      }),
    );
    setup("/enquiries/7/details");
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    await waitFor(() => expect(screen.getAllByText("E-XYZ-007").length).toBeGreaterThan(0));
  });

  it("renders the Activity tab from the array endpoint", async () => {
    asReservationsUser();
    server.use(
      http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)),
      http.get("/api/v1/enquiries/7/activity", () =>
        HttpResponse.json([
          {
            id: 1,
            enquiry: 7,
            from_status: "new",
            to_status: "contacted",
            kind: "contacted",
            actor: null,
            source: "user",
            reason: "Reached out by email",
            meta: {},
            created_at: "2026-05-03T00:00:00Z",
          },
        ]),
      ),
    );
    setup("/enquiries/7/activity");
    expect(await screen.findByText("new → contacted")).toBeInTheDocument();
    expect(screen.getByText(/Reached out by email/i)).toBeInTheDocument();
  });
});
