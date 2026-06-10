import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { EnquiryDetailLayout } from "../EnquiryDetailLayout";
import type { QuotationDetail } from "@/features/quotations/schemas";

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
  phone: "",
  contact_method: null,
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
  quotations: [] as QuotationDetail[],
};

const quotedEnquiry = {
  ...baseEnquiry,
  status: "quoted" as const,
  quotations: [
    {
      id: 50,
      reference: "QVC50",
      status: "draft",
      is_unbranded: false,
      cancel_reason: "",
      lines: [],
    },
  ] satisfies QuotationDetail[],
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
    preferred_language: "en",
    ...overrides,
  };
}

function asReservationsUser() {
  useAuthStore
    .getState()
    .setMe(makeUser(), { role: "RESERVATIONS", is_superuser: false, permissions: [] });
}

function asViewerUser() {
  useAuthStore
    .getState()
    .setMe(makeUser(), { role: "VIEWER", is_superuser: false, permissions: [] });
}

// Routes mirror the app: the workspace plus the three legacy sub-route
// redirects (Details/Activity/Notes collapsed into the single page).
function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/enquiries/:id" element={<EnquiryDetailLayout />} />
      <Route path="/enquiries/:id/details" element={<Navigate to=".." relative="path" replace />} />
      <Route
        path="/enquiries/:id/activity"
        element={<Navigate to=".." relative="path" replace />}
      />
      <Route path="/enquiries/:id/notes" element={<Navigate to=".." relative="path" replace />} />
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
    setup("/enquiries/7");
    await waitFor(() => expect(screen.getAllByText("E-XYZ-007").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Ada Lovelace").length).toBeGreaterThan(0);
  });

  it("enables Close + Assign on a new enquiry, disables Reopen", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7");
    await screen.findByRole("button", { name: /assign/i });

    expect(screen.getByRole("button", { name: /assign/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /reopen/i })).toBeDisabled();
  });

  it("enables Reopen + disables Close when status is lost", async () => {
    asReservationsUser();
    server.use(
      http.get("/api/v1/enquiries/7", () =>
        HttpResponse.json({ ...baseEnquiry, status: "lost", quotations: [] }),
      ),
    );
    setup("/enquiries/7");
    await screen.findByRole("button", { name: /reopen/i });

    expect(screen.getByRole("button", { name: /reopen/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeDisabled();
  });

  it("disables every action when the user lacks the reservations role", async () => {
    asViewerUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7");
    await screen.findByRole("button", { name: /assign/i });
    expect(screen.getByRole("button", { name: /assign/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /close as lost/i })).toBeDisabled();
  });

  it("renders 'not found' (no retry) on 404", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json({}, { status: 404 })));
    setup("/enquiries/7");
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
    setup("/enquiries/7");
    const retry = await screen.findByRole("button", { name: /retry/i });
    await userEvent.click(retry);
    await waitFor(() => expect(screen.getAllByText("E-XYZ-007").length).toBeGreaterThan(0));
  });

  it("renders the inline quote-stack and defaults the builder open when there are no quotes", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)));
    setup("/enquiries/7");
    // No quotes → empty state + builder expanded (the search button is visible).
    expect(await screen.findByText(/no quotes for this enquiry/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search options/i })).toBeInTheDocument();
  });

  it("renders existing quotes and keeps the builder collapsed until invoked", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(quotedEnquiry)));
    setup("/enquiries/7");

    expect(await screen.findByRole("link", { name: /QVC50/ })).toHaveAttribute(
      "href",
      "/enquiries/quotes/50",
    );
    // Builder collapsed → no search button yet.
    expect(screen.queryByRole("button", { name: /search options/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /build another quote/i }));
    expect(await screen.findByRole("button", { name: /search options/i })).toBeInTheDocument();
  });

  it("does not fetch the activity timeline until the rail panel is expanded", async () => {
    asReservationsUser();
    let activityCalls = 0;
    server.use(
      http.get("/api/v1/enquiries/7", () => HttpResponse.json(quotedEnquiry)),
      http.get("/api/v1/enquiries/7/activity", () => {
        activityCalls += 1;
        return HttpResponse.json([
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
        ]);
      }),
    );
    setup("/enquiries/7");
    await screen.findByRole("button", { name: /assign/i });

    // Collapsed by default — the timeline must not have been requested.
    expect(activityCalls).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: /^activity$/i }));
    expect(await screen.findByText("new → contacted")).toBeInTheDocument();
    expect(activityCalls).toBe(1);
  });

  it("suppresses the inline builder and disables the toggle on a lost enquiry", async () => {
    asReservationsUser();
    server.use(
      http.get("/api/v1/enquiries/7", () =>
        HttpResponse.json({ ...baseEnquiry, status: "lost", quotations: [] }),
      ),
    );
    setup("/enquiries/7");
    // Builder must not auto-open for a final enquiry (no search button), and the
    // build toggle is disabled — quoting a lost enquiry is blocked.
    await screen.findByRole("button", { name: /assign/i });
    expect(screen.queryByRole("button", { name: /search options/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /build a quote/i })).toBeDisabled();
  });

  it("re-evaluates the builder open-state when navigating between enquiries", async () => {
    asReservationsUser();
    const quotedEnquiry8 = { ...quotedEnquiry, id: 8 };
    server.use(
      http.get("/api/v1/enquiries/7", () => HttpResponse.json(baseEnquiry)),
      http.get("/api/v1/enquiries/8", () => HttpResponse.json(quotedEnquiry8)),
    );

    function NavTo({ id }: { id: number }) {
      const navigate = useNavigate();
      return <button onClick={() => navigate(`/enquiries/${id}`)}>go-{id}</button>;
    }

    renderWithProviders(
      <>
        <NavTo id={8} />
        <Routes>
          <Route path="/enquiries/:id" element={<EnquiryDetailLayout />} />
        </Routes>
      </>,
      { route: "/enquiries/7" },
    );

    // Enquiry 7 has no quotes → builder auto-opens.
    expect(await screen.findByRole("button", { name: /search options/i })).toBeInTheDocument();

    // Navigate to enquiry 8 (already quoted): the section remounts on the new
    // id, so the builder must be collapsed — not carried open from enquiry 7.
    await userEvent.click(screen.getByRole("button", { name: /go-8/i }));
    await screen.findByRole("link", { name: /QVC50/ });
    expect(screen.queryByRole("button", { name: /search options/i })).not.toBeInTheDocument();
  });

  it("redirects the legacy /details deep link to the unified workspace", async () => {
    asReservationsUser();
    server.use(http.get("/api/v1/enquiries/7", () => HttpResponse.json(quotedEnquiry)));
    setup("/enquiries/7/details");
    // Landed on the workspace (quote-stack visible), not a 404.
    expect(await screen.findByRole("link", { name: /QVC50/ })).toBeInTheDocument();
  });
});
