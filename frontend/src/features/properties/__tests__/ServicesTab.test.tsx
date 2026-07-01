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
import { ServicesTab } from "../tabs/ServicesTab";

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

const chef = {
  id: 300,
  property: 7,
  name: "Private chef",
  copy: "A private chef prepares dinner nightly.",
  notes: "Summer only — confirm with owner.",
  applies_from: "2026-06-01",
  applies_to: "2026-08-31",
  sort_order: 0,
  is_active: true,
};

const housekeeping = {
  id: 301,
  property: 7,
  name: "Housekeeping",
  copy: "Daily housekeeping is included.",
  notes: null,
  applies_from: null,
  applies_to: null,
  sort_order: 1,
  is_active: true,
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

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="services" replace />} />
        <Route path="services" element={<ServicesTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/services" },
  );
}

describe("ServicesTab", () => {
  it("renders rows with name, date band, and guest copy", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/services", () =>
        HttpResponse.json(drfPage([chef, housekeeping])),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Private chef")).toBeInTheDocument());
    // Banded service shows its absolute date range.
    expect(screen.getByText("2026-06-01 – 2026-08-31")).toBeInTheDocument();
    expect(screen.getByText(/A private chef prepares dinner/i)).toBeInTheDocument();
    // Open-ended service (null band) shows the year-round label.
    expect(screen.getByText("Housekeeping")).toBeInTheDocument();
    expect(screen.getByText(/Year-round/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows the empty state when there are no services", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByText(/No services yet/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("swaps sort_order on move-down via two flat PATCH calls", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/services", () =>
        HttpResponse.json(drfPage([chef, housekeeping])),
      ),
    );
    const patched: Array<{ id: number; sort_order?: number }> = [];
    server.use(
      http.patch("/api/v1/services/:serviceId", async ({ params, request }) => {
        const body = (await request.json()) as { sort_order?: number };
        const id = Number(params.serviceId);
        patched.push({ id, sort_order: body.sort_order });
        const ret = id === chef.id ? chef : housekeeping;
        return HttpResponse.json({ ...ret, sort_order: body.sort_order ?? ret.sort_order });
      }),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Private chef")).toBeInTheDocument());
    const moveDown = screen.getAllByRole("button", { name: /move down/i })[0];
    await userEvent.click(moveDown);
    await waitFor(() => expect(patched.length).toBe(2));
    expect(patched.map((p) => p.id).sort()).toEqual([300, 301]);
    useAuthStore.getState().clear();
  });

  it("deletes a service through the confirm dialog via the flat DELETE route", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([chef]))));
    let deleteCalled = false;
    server.use(
      http.delete("/api/v1/services/300", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Private chef")).toBeInTheDocument());
    await userEvent.click(await screen.findByRole("button", { name: /actions/i }));
    await userEvent.click(await screen.findByText(/^Delete$/i));
    await userEvent.click(await screen.findByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(deleteCalled).toBe(true));
    useAuthStore.getState().clear();
  });
});
