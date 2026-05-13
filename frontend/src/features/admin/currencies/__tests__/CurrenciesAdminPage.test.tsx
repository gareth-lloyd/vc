import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { CurrenciesAdminPage } from "../CurrenciesAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, code: "GBP", name: "Pound sterling", symbol: "£", decimal_places: 2, is_active: true },
    { id: 2, code: "EUR", name: "Euro", symbol: "€", decimal_places: 2, is_active: true },
  ],
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

describe("CurrenciesAdminPage", () => {
  it("renders rows", async () => {
    server.use(http.get("/api/v1/currencies", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/admin/currencies" element={<CurrenciesAdminPage />} />
      </Routes>,
      { route: "/admin/currencies" },
    );
    expect(await screen.findByText("Pound sterling")).toBeInTheDocument();
    expect(screen.getByText("Euro")).toBeInTheDocument();
  });
});
