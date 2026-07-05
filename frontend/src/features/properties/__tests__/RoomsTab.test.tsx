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
import { RoomsTab } from "../tabs/RoomsTab";

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

const roomA = {
  id: 200,
  property: 7,
  name: "Master bedroom",
  placement: "main_house",
  website_description: "",
  vc_notes: "",
  is_ensuite: true,
  sort_order: 0,
  beds: {
    double: 1,
    twin_double: 0,
    twin: 0,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  },
};

const roomB = {
  id: 201,
  property: 7,
  name: "Twin room",
  placement: "main_house",
  website_description: "",
  vc_notes: "",
  is_ensuite: false,
  sort_order: 1,
  beds: {
    double: 0,
    twin_double: 0,
    twin: 2,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  },
};

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)));
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

function setReadonlyUser() {
  useAuthStore.getState().setMe(
    {
      id: 2,
      email: "r@test.com",
      first_name: "R",
      last_name: "T",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      preferred_language: "en",
      role: "READONLY",
    },
    { role: "READONLY", is_superuser: false, permissions: [] },
  );
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="rooms" replace />} />
        <Route path="rooms" element={<RoomsTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/rooms" },
  );
}

// GAP-064: facets + assigned amenities (attribute_links read shape).
const roomC = {
  ...roomA,
  id: 202,
  name: "Garden suite",
  is_ensuite: true,
  ensuite_type: "shower",
  access: "outside",
  sort_order: 2,
  attribute_links: [
    {
      id: 90,
      attribute: 1,
      slug: "wardrobe",
      name: "Wardrobe",
      icon: "shirt",
      is_active: true,
      note: "",
    },
    {
      id: 91,
      attribute: 3,
      slug: "fireplace",
      name: "Fireplace",
      icon: "flame",
      is_active: false,
      note: "gas",
    },
  ],
};

describe("RoomsTab", () => {
  it("renders rows with placement badge and bed summary", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomA, roomB]))),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Master bedroom")).toBeInTheDocument());
    expect(screen.getByText("Twin room")).toBeInTheDocument();
    expect(screen.getByText(/1 double/i)).toBeInTheDocument();
    expect(screen.getByText(/2 twins/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("renders amenity chips and facet badges for a room with attribute_links (GAP-064)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomC]))));
    setup();
    await waitFor(() => expect(screen.getByText("Garden suite")).toBeInTheDocument());
    // Amenity chips render name (icon is decorative) — retired links included.
    expect(screen.getByText("Wardrobe")).toBeInTheDocument();
    expect(screen.getByText("Fireplace")).toBeInTheDocument();
    // Ensuite badge carries the type; access surfaces as its own badge.
    expect(screen.getByText(/Ensuite · Shower/i)).toBeInTheDocument();
    expect(screen.getByText(/^Outside$/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows empty state when there are no rooms", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByText(/No rooms yet/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("disables Add room when the user lacks the RESERVATIONS role", async () => {
    setReadonlyUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add room/i });
    expect(btn).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("opens the Add room dialog when role allows", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add room/i });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    expect(await screen.findByLabelText(/^Name$/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("deletes a room via the menu and confirm dialog", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomA]))));
    let deleteCalled = false;
    server.use(
      http.delete("/api/v1/properties/7/rooms/200", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    setup();
    await waitFor(() => expect(screen.getByText("Master bedroom")).toBeInTheDocument());
    const menu = await screen.findByRole("button", { name: /actions/i });
    await userEvent.click(menu);
    const deleteItem = await screen.findByText(/^Delete$/i);
    await userEvent.click(deleteItem);
    const confirm = await screen.findByRole("button", { name: /^Remove$/i });
    await userEvent.click(confirm);
    await waitFor(() => expect(deleteCalled).toBe(true));
    useAuthStore.getState().clear();
  });
});
