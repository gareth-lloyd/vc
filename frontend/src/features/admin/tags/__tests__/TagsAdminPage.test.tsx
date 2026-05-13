import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { TagsAdminPage } from "../TagsAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const categoriesFixture = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      name: "Outdoor",
      slug: "outdoor",
      description: "",
      icon: "",
      sort_order: 0,
      is_active: true,
    },
  ],
};

const featuresFixture = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 10,
      category: 1,
      name: "Pool",
      slug: "pool",
      description: "",
      icon: "",
      sort_order: 0,
      is_active: true,
      service_type: "amenity",
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

describe("TagsAdminPage", () => {
  it("renders categories and features", async () => {
    server.use(
      http.get("/api/v1/feature-categories", () => HttpResponse.json(categoriesFixture)),
      http.get("/api/v1/features", () => HttpResponse.json(featuresFixture)),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    const outdoor = await screen.findAllByText("Outdoor");
    expect(outdoor.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("Pool")).toBeInTheDocument();
  });
});
