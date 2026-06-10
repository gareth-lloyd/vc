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
import { MediaTab } from "../tabs/MediaTab";

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

const imageA = {
  id: 100,
  property: 7,
  image_url: "/media/properties/2026/05/hero.jpg",
  kind: "hero",
  name: "Front view",
  description: "",
  sort_order: 0,
  is_active: true,
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

const imageB = {
  id: 101,
  property: 7,
  image_url: "/media/properties/2026/05/garden.jpg",
  kind: "gallery",
  name: "Garden",
  description: "",
  sort_order: 1,
  is_active: true,
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
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
        <Route index element={<Navigate to="media" replace />} />
        <Route path="media" element={<MediaTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/media" },
  );
}

describe("MediaTab", () => {
  it("renders image cards with hero badge for hero kind", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([imageA, imageB]))),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Front view")).toBeInTheDocument());
    expect(screen.getByText("Garden")).toBeInTheDocument();
    expect(screen.getByText("Hero")).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows empty state when there are no images", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByText(/No images yet/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("calls set-hero endpoint when 'Set as hero' is clicked", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([imageA, imageB]))),
    );

    let setHeroCalledWith: { image_id?: number } | null = null;
    server.use(
      http.post("/api/v1/properties/7/images:set-hero", async ({ request }) => {
        setHeroCalledWith = (await request.json()) as { image_id?: number };
        return HttpResponse.json({}, { status: 200 });
      }),
    );

    setup();
    await waitFor(() => expect(screen.getByText("Garden")).toBeInTheDocument());

    const menus = screen.getAllByRole("button", { name: /actions/i });
    // imageA (hero) is first → its menu has no "Set as hero". Use imageB's menu.
    await userEvent.click(menus[1]);
    const setHero = await screen.findByText(/Set as hero/i);
    await userEvent.click(setHero);

    await waitFor(() => expect(setHeroCalledWith).not.toBeNull());
    expect(setHeroCalledWith).toEqual({ image_id: 101 });
    useAuthStore.getState().clear();
  });

  it("disables Add image button when user lacks RESERVATIONS role", async () => {
    setReadonlyUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add image/i });
    expect(btn).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("opens the Add image dialog when role allows", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add image/i });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    expect(await screen.findByLabelText(/image file/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("uploads the chosen file as multipart form data", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([]))));

    let received: { filename?: string; kind?: string } | null = null;
    server.use(
      http.post("/api/v1/properties/7/images", async ({ request }) => {
        const form = await request.formData();
        const file = form.get("image");
        received = {
          filename: file instanceof File ? file.name : undefined,
          kind: String(form.get("kind")),
        };
        return HttpResponse.json(imageA, { status: 201 });
      }),
    );

    setup();
    await userEvent.click(await screen.findByRole("button", { name: /add image/i }));
    const fileInput = await screen.findByLabelText(/image file/i);
    await userEvent.upload(fileInput, new File(["png-bytes"], "pool.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(received).toEqual({ filename: "pool.png", kind: "gallery" }));
    useAuthStore.getState().clear();
  });

  it("requires a file before submitting a new image", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/images", () => HttpResponse.json(drfPage([]))));
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /add image/i }));
    await screen.findByLabelText(/image file/i);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/choose an image file/i);
    useAuthStore.getState().clear();
  });
});
