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
import { NearbyTab } from "../tabs/NearbyTab";

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
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const placeTypes = [
  { id: 1, name: "Beach", icon: "" },
  { id: 2, name: "Restaurant", icon: "" },
];

const placeA = {
  id: 300,
  property: 7,
  place_type: 1,
  name: "South beach",
  distance_km: "0.50",
  notes: "Family-friendly cove",
  sort_order: 0,
};

const placeB = {
  id: 301,
  property: 7,
  place_type: 2,
  name: "Trattoria",
  distance_km: "1.20",
  notes: "",
  sort_order: 1,
};

function installBaseHandlers() {
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/nearby-place-types", () => HttpResponse.json(drfPage(placeTypes))),
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
        <Route index element={<Navigate to="nearby" replace />} />
        <Route path="nearby" element={<NearbyTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/nearby" },
  );
}

describe("NearbyTab", () => {
  it("renders rows with place type name and distance", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/nearby", () => HttpResponse.json(drfPage([placeA, placeB]))),
    );
    setup();
    await waitFor(() => expect(screen.getByText("South beach")).toBeInTheDocument());
    expect(screen.getByText(/Beach · 0\.5 km/i)).toBeInTheDocument();
    expect(screen.getByText("Trattoria")).toBeInTheDocument();
    expect(screen.getByText(/Restaurant · 1\.2 km/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows empty state when there are no places", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/nearby", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByText(/No nearby places yet/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("swaps sort_order on move-down via two PATCH calls", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/nearby", () => HttpResponse.json(drfPage([placeA, placeB]))),
    );
    const patched: Array<{ id: number; sort_order?: number }> = [];
    server.use(
      http.patch("/api/v1/properties/7/nearby/:poiId", async ({ params, request }) => {
        const body = (await request.json()) as { sort_order?: number };
        const id = Number(params.poiId);
        patched.push({ id, sort_order: body.sort_order });
        const ret = id === placeA.id ? placeA : placeB;
        return HttpResponse.json({ ...ret, sort_order: body.sort_order ?? ret.sort_order });
      }),
    );
    setup();
    await waitFor(() => expect(screen.getByText("South beach")).toBeInTheDocument());
    const moveDown = screen.getAllByRole("button", { name: /move down/i })[0];
    await userEvent.click(moveDown);
    await waitFor(() => expect(patched.length).toBe(2));
    const ids = patched.map((p) => p.id).sort();
    expect(ids).toEqual([300, 301]);
    useAuthStore.getState().clear();
  });

  it("opens the Add place dialog and shows place type options", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/nearby", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add place/i });
    await userEvent.click(btn);
    expect(await screen.findByLabelText(/^Name$/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});
