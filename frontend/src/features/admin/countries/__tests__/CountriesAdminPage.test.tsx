import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { CountriesAdminPage } from "../CountriesAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      iso2: "GB",
      name: "United Kingdom",
      iso3: "GBR",
      dial_code: "+44",
      default_tax_rate: null,
      sort_order: 0,
      is_active: true,
    },
    {
      id: 2,
      iso2: "FR",
      name: "France",
      iso3: "FRA",
      dial_code: "+33",
      default_tax_rate: null,
      sort_order: 0,
      is_active: true,
    },
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

function asAdmin() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "admin",
    is_superuser: false,
    permissions: [],
  });
}

beforeEach(() => {
  useAuthStore.getState().clear();
});
afterEach(() => {
  server.resetHandlers();
});

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/countries" element={<CountriesAdminPage />} />
    </Routes>,
    { route: "/admin/countries" },
  );
}

describe("CountriesAdminPage", () => {
  it("renders rows", async () => {
    asAdmin();
    server.use(http.get("/api/v1/countries", () => HttpResponse.json(fixture)));
    setup();
    expect(await screen.findByText("United Kingdom")).toBeInTheDocument();
    expect(screen.getByText("France")).toBeInTheDocument();
  });

  it("opens the create dialog for admins", async () => {
    asAdmin();
    server.use(http.get("/api/v1/countries", () => HttpResponse.json(fixture)));
    setup();
    await screen.findByText("United Kingdom");
    await userEvent.click(screen.getByRole("button", { name: /new country/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toHaveTextContent(/new country/i));
  });
});
