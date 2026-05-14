import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

describe("FeaturesTab", () => {
  it("renders features grouped by category with the initial selection checked", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    await waitFor(() => expect(screen.getByText("Outdoor")).toBeInTheDocument());
    expect(screen.getByText("Indoor")).toBeInTheDocument();
    const poolCheckbox = screen.getByLabelText("Pool");
    expect(poolCheckbox).toBeChecked();
    const bbqCheckbox = screen.getByLabelText("BBQ");
    expect(bbqCheckbox).not.toBeChecked();
    useAuthStore.getState().clear();
  });

  it("disables Save until a change has been made", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    const save = await screen.findByRole("button", { name: /save changes/i });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByLabelText("BBQ"));
    expect(save).toBeEnabled();
    useAuthStore.getState().clear();
  });

  it("PATCHes /properties/{id} with the full features array on Save", async () => {
    setReservationsUser();
    installBaseHandlers();
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({
          ...propertyFixture,
          feature_ids: patchedBody?.features ?? [],
        });
      }),
    );
    setup();
    await userEvent.click(await screen.findByLabelText("BBQ"));
    await userEvent.click(await screen.findByLabelText("Wi-Fi"));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchedBody).not.toBeNull());
    const ids = patchedBody!.features?.sort() ?? [];
    expect(ids).toEqual([11, 12, 13]);
    useAuthStore.getState().clear();
  });

  it("resets local selection on Reset", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    const bbq = await screen.findByLabelText("BBQ");
    await userEvent.click(bbq);
    expect(bbq).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(bbq).not.toBeChecked();
    useAuthStore.getState().clear();
  });
});
