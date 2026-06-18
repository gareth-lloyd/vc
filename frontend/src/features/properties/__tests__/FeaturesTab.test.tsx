import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { FeaturesTab } from "../tabs/FeaturesTab";

const propertyFixture = {
  id: 7,
  name: "Casa Sur",
  display_name: "Casa Sur",
  slug: "casa-sur",
  licence_number: "ETV-7777",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [11],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const categories = [
  {
    id: 1,
    name: "Outdoor",
    slug: "outdoor",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
  },
  {
    id: 2,
    name: "Indoor",
    slug: "indoor",
    description: "",
    icon: "",
    sort_order: 2,
    is_active: true,
  },
];

const features = [
  {
    id: 11,
    category: 1,
    name: "Pool",
    slug: "pool",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 12,
    category: 1,
    name: "BBQ",
    slug: "bbq",
    description: "",
    icon: "",
    sort_order: 2,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 13,
    category: 2,
    name: "Wi-Fi",
    slug: "wifi",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
];

function installBaseHandlers() {
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/features", () => HttpResponse.json(drfPage(features))),
    http.get("/api/v1/feature-categories", () => HttpResponse.json(drfPage(categories))),
  );
}

function setReservationsUser() {
  useAuthStore.getState().setMe(
    {
      id: 1,
      email: "a@test.com",
      first_name: "A",
      last_name: "T",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      preferred_language: "en",
      role: "RESERVATIONS",
    },
    { role: "RESERVATIONS", is_superuser: false, permissions: [] },
  );
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="features" replace />} />
        <Route path="features" element={<FeaturesTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/features" },
  );
}

function featureRow(id: number) {
  return screen.getByTestId(`property-feature-row-${id}`);
}

afterEach(() => {
  useAuthStore.getState().clear();
});

describe("FeaturesTab", () => {
  it("renders the selected features as an ordered list; unselected stay out of it", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    await waitFor(() => expect(featureRow(11)).toBeInTheDocument());
    expect(within(featureRow(11)).getByText("Pool")).toBeInTheDocument();
    // BBQ / Wi-Fi are unselected — not rendered as rows.
    expect(screen.queryByTestId("property-feature-row-12")).not.toBeInTheDocument();
    expect(screen.queryByTestId("property-feature-row-13")).not.toBeInTheDocument();
  });

  it("disables Save until the selection changes, then adds a feature via the Add menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    const save = await screen.findByRole("button", { name: /save changes/i });
    expect(save).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));

    expect(featureRow(12)).toBeInTheDocument();
    expect(save).toBeEnabled();
  });

  it("PATCHes /properties/{id} with the features in LIST ORDER (not sorted)", async () => {
    setReservationsUser();
    installBaseHandlers();
    // Start with Wi-Fi(13) before Pool(11) so a naive sort would reorder them;
    // the payload must preserve list order — the GAP-022 sort_order contract.
    server.use(
      http.get("/api/v1/properties/casa-sur", () =>
        HttpResponse.json({ ...propertyFixture, feature_ids: [13, 11] }),
      ),
    );
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({ ...propertyFixture, feature_ids: patchedBody?.features ?? [] });
      }),
    );
    setup();

    // Append BBQ(12) last — it must land at the end of the ordered payload.
    await userEvent.click(await screen.findByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody!.features).toEqual([13, 11, 12]);
  });

  it("removes a feature from the selection", async () => {
    setReservationsUser();
    installBaseHandlers();
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({ ...propertyFixture, feature_ids: patchedBody?.features ?? [] });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /remove pool/i }));
    expect(screen.queryByTestId("property-feature-row-11")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody!.features).toEqual([]);
  });

  it("reverts local edits on Reset", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));
    expect(featureRow(12)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(screen.queryByTestId("property-feature-row-12")).not.toBeInTheDocument();
  });
});
