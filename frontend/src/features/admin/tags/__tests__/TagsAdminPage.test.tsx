import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { TagsAdminPage } from "../TagsAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const categoriesFixture = {
  count: 3,
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
    {
      id: 2,
      name: "Kitchen",
      slug: "kitchen",
      description: "",
      icon: "",
      sort_order: 1,
      is_active: true,
    },
    {
      id: 8,
      name: "Other Information Tags",
      slug: "other-information",
      description: "",
      icon: "info",
      sort_order: 60,
      is_active: true,
    },
  ],
};

const allFeatures = [
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
  {
    id: 11,
    category: 2,
    name: "Oven",
    slug: "oven",
    description: "",
    icon: "",
    sort_order: 0,
    is_active: true,
    // Omitted deliberately — exercises featureSchema's service_type
    // .default("amenity") fallback (a legacy row without the field).
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
  useAuthStore.getState().setMe(makeUser(), {
    role: "admin",
    is_superuser: false,
    permissions: [],
  });
  // The `category` query param must actually narrow the response — the live
  // bug (BUG-019 #3) was `FeatureViewSet` ignoring it, and a stub that always
  // returns the same fixture regardless of the query string makes that
  // invisible to the suite.
  server.use(
    http.get("/api/v1/feature-categories", () => HttpResponse.json(categoriesFixture)),
    http.get("/api/v1/features", ({ request }) => {
      const category = new URL(request.url).searchParams.get("category");
      const results = category
        ? allFeatures.filter((f) => String(f.category) === category)
        : allFeatures;
      return HttpResponse.json({ count: results.length, next: null, previous: null, results });
    }),
  );
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("TagsAdminPage", () => {
  it("renders categories and features", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    const outdoor = await screen.findAllByText("Outdoor");
    expect(outdoor.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("Pool")).toBeInTheDocument();
    expect(await screen.findByText("Oven")).toBeInTheDocument();
  });

  it("selecting a category actually filters the features table", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    expect(await screen.findByText("Pool")).toBeInTheDocument();
    expect(await screen.findByText("Oven")).toBeInTheDocument();

    const trigger = screen.getByRole("combobox", { name: /category/i });
    await user.click(trigger);
    await user.click(await screen.findByRole("option", { name: "Outdoor" }));

    await waitFor(() => {
      expect(screen.getByText("Pool")).toBeInTheDocument();
      expect(screen.queryByText("Oven")).not.toBeInTheDocument();
    });
  });

  it("locks the reserved other-information slug in the category edit dialog", async () => {
    // The Features tab, Zoho export and seeding key on `other-information`;
    // a rename through this dialog silently emptied all three.
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    const row = (await screen.findByText("Other Information Tags")).closest("tr");
    if (!row) throw new Error("row not found");
    await user.click(within(row).getByRole("button", { name: "Open row actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Edit" }));

    const slug = await screen.findByLabelText("Slug");
    expect(slug).toBeDisabled();
    expect(slug).toHaveValue("other-information");
    expect(screen.getByText(/slug is reserved/i)).toBeInTheDocument();
  });

  it("leaves an ordinary category's slug editable", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    const row = (await screen.findAllByText("Outdoor"))[0]?.closest("tr");
    if (!row) throw new Error("row not found");
    await user.click(within(row).getByRole("button", { name: "Open row actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Edit" }));

    expect(await screen.findByLabelText("Slug")).toBeEnabled();
    expect(screen.queryByText(/slug is reserved/i)).not.toBeInTheDocument();
  });

  it("features table pagination is wired to real query params, not hardcoded to page 1", async () => {
    server.use(
      http.get("/api/v1/features", ({ request }) => {
        const url = new URL(request.url);
        const page = url.searchParams.get("page");
        // 120 features, 50 per page (the DataTable default) → page 2 exists.
        const count = 120;
        const results =
          page === "2" ? [{ ...allFeatures[0], id: 999, name: "Page Two Feature" }] : allFeatures;
        return HttpResponse.json({
          count,
          next: page === "2" ? null : "?page=2",
          previous: null,
          results,
        });
      }),
    );
    renderWithProviders(
      <Routes>
        <Route path="/admin/tags" element={<TagsAdminPage />} />
      </Routes>,
      { route: "/admin/tags" },
    );
    expect(await screen.findByText("Pool")).toBeInTheDocument();

    const featuresSection = screen.getByText("Pool").closest("section");
    expect(featuresSection).not.toBeNull();
    const nextButton = within(featuresSection as HTMLElement).getByRole("button", {
      name: /next/i,
    });
    await userEvent.setup().click(nextButton);

    expect(await screen.findByText("Page Two Feature")).toBeInTheDocument();
  });
});
