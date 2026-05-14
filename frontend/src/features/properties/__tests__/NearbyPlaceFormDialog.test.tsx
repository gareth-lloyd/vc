import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { NearbyPlaceFormDialog } from "../components/NearbyPlaceFormDialog";

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

const placeTypes = [{ id: 1, name: "Beach", icon: "" }];

describe("NearbyPlaceFormDialog", () => {
  it("submits a new place on save", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/nearby-place-types", () => HttpResponse.json(drfPage(placeTypes))),
    );
    let posted: unknown = null;
    server.use(
      http.post("/api/v1/properties/7/nearby", async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          {
            id: 999,
            property: 7,
            place_type: 1,
            name: "Beach",
            distance_km: "0.50",
            notes: "",
            sort_order: 0,
          },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(
      <NearbyPlaceFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );

    await userEvent.type(await screen.findByLabelText(/^Name$/i), "South cove");
    await userEvent.type(screen.getByLabelText(/distance/i), "0.5");

    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "Beach" }));

    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(posted).not.toBeNull());
    expect((posted as { name?: string }).name).toBe("South cove");
    expect((posted as { distance_km?: string }).distance_km).toBe("0.5");
    expect((posted as { place_type?: number }).place_type).toBe(1);
    useAuthStore.getState().clear();
  });

  it("rejects an invalid distance via Zod and does not POST", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/nearby-place-types", () => HttpResponse.json(drfPage(placeTypes))),
    );
    let postCalled = false;
    server.use(
      http.post("/api/v1/properties/7/nearby", () => {
        postCalled = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderWithProviders(
      <NearbyPlaceFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "X");
    await userEvent.type(screen.getByLabelText(/distance/i), "abc");
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "Beach" }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(
        screen
          .getByLabelText(/distance/i)
          .closest("div")
          ?.querySelector('[role="alert"]'),
      ).toBeInTheDocument(),
    );
    expect(postCalled).toBe(false);
    useAuthStore.getState().clear();
  });
});
