import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { EmailTemplatesListPage } from "../EmailTemplatesListPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const ROWS = [
  {
    key: "booking.confirmation",
    title: "Booking Confirmation",
    version: 3,
    is_active: true,
    updated_at: "2026-01-02T10:00:00Z",
    updated_by_id: 1,
  },
  {
    key: "payment.receipt",
    title: "Payment Receipt",
    version: 1,
    is_active: true,
    updated_at: "2026-01-03T10:00:00Z",
    updated_by_id: null,
  },
];

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

beforeEach(() => {
  useAuthStore
    .getState()
    .setMe(makeUser(), { role: "admin", is_superuser: false, permissions: [] });
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("EmailTemplatesListPage", () => {
  it("renders the template catalogue", async () => {
    server.use(http.get("/api/v1/email-templates", () => HttpResponse.json(drfPage(ROWS))));
    renderWithProviders(
      <Routes>
        <Route path="/admin/email-templates" element={<EmailTemplatesListPage />} />
      </Routes>,
      { route: "/admin/email-templates" },
    );
    expect(await screen.findByText("Booking Confirmation")).toBeInTheDocument();
    expect(screen.getByText("Payment Receipt")).toBeInTheDocument();
    // The dotted key is still shown as a subtitle.
    expect(screen.getByText("booking.confirmation")).toBeInTheDocument();
  });

  it("navigates to the template detail on row click", async () => {
    server.use(http.get("/api/v1/email-templates", () => HttpResponse.json(drfPage(ROWS))));
    renderWithProviders(
      <Routes>
        <Route path="/admin/email-templates" element={<EmailTemplatesListPage />} />
        <Route path="/admin/email-templates/:key" element={<div>detail page</div>} />
      </Routes>,
      { route: "/admin/email-templates" },
    );
    await userEvent.click(await screen.findByText("booking.confirmation"));
    expect(await screen.findByText("detail page")).toBeInTheDocument();
  });

  it("shows the empty state when there are no templates", async () => {
    server.use(http.get("/api/v1/email-templates", () => HttpResponse.json(drfPage([]))));
    renderWithProviders(
      <Routes>
        <Route path="/admin/email-templates" element={<EmailTemplatesListPage />} />
      </Routes>,
      { route: "/admin/email-templates" },
    );
    expect(await screen.findByText("No templates yet")).toBeInTheDocument();
  });
});
