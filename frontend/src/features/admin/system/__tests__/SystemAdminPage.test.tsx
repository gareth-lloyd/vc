import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { SystemAdminPage } from "../SystemAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

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
  useAuthStore.getState().setMe(makeUser(), {
    role: "admin",
    is_superuser: false,
    permissions: [],
  });
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("SystemAdminPage", () => {
  it("renders existing settings as editable rows", async () => {
    server.use(
      http.get("/api/v1/system/settings", () =>
        HttpResponse.json({
          settings: { feature_flag_a: "on", max_guests: 8 },
          updated_at: "2025-01-01T00:00:00Z",
        }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/system" element={<SystemAdminPage />} />
      </Routes>,
      { route: "/admin/system" },
    );
    expect(await screen.findByText("feature_flag_a")).toBeInTheDocument();
    expect(screen.getByText("max_guests")).toBeInTheDocument();
  });

  it("shows the human-readable label for a known catalog key", async () => {
    server.use(
      http.get("/api/v1/system/settings", () =>
        HttpResponse.json({
          settings: { quotation_no_prefix: "QVC" },
          updated_at: "2025-01-01T00:00:00Z",
        }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/system" element={<SystemAdminPage />} />
      </Routes>,
      { route: "/admin/system" },
    );
    // Friendly label is the primary heading; the raw key stays as a hint.
    expect(await screen.findByText("Quotation number prefix")).toBeInTheDocument();
    expect(screen.getByText("quotation_no_prefix")).toBeInTheDocument();
  });

  it("adds a setting by picking it from the catalog dropdown", async () => {
    server.use(
      http.get("/api/v1/system/settings", () =>
        HttpResponse.json({ settings: {}, updated_at: null }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/system" element={<SystemAdminPage />} />
      </Routes>,
      { route: "/admin/system" },
    );
    await userEvent.click(await screen.findByRole("button", { name: /add setting/i }));
    // Open the catalog dropdown and pick a known setting by its friendly label.
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "Booking number prefix" }));
    // The value pre-fills with the platform default.
    expect(await screen.findByDisplayValue("VC")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    // The new row lands with its friendly label.
    expect(await screen.findByText("Booking number prefix")).toBeInTheDocument();
  });

  it("PATCHes settings on save", async () => {
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/system/settings", () =>
        HttpResponse.json({
          settings: { flag_a: "old" },
          updated_at: "2025-01-01T00:00:00Z",
        }),
      ),
      http.patch("/api/v1/system/settings", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          settings: { flag_a: "new" },
          updated_at: "2025-01-02T00:00:00Z",
        });
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/system" element={<SystemAdminPage />} />
      </Routes>,
      { route: "/admin/system" },
    );
    const input = await screen.findByDisplayValue("old");
    await userEvent.clear(input);
    await userEvent.type(input, "new");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    const body = patchBody as Record<string, unknown> | null;
    expect((body?.settings as Record<string, unknown>).flag_a).toBe("new");
  });
});
