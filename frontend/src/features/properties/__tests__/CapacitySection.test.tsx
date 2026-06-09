import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { CapacitySection } from "../components/CapacitySection";

function makeCapacity(overrides: Record<string, unknown> = {}) {
  return {
    property: 9,
    guests: 8,
    additional_guests: 2,
    bedrooms: 4,
    ensuites: 3,
    bathrooms: 5,
    size_sqm: "240.50",
    ...overrides,
  };
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

describe("CapacitySection", () => {
  it("renders the form seeded from the loaded capacity", async () => {
    setReservationsUser();
    server.use(http.get("/api/v1/properties/9/capacity", () => HttpResponse.json(makeCapacity())));
    renderWithProviders(<CapacitySection propertyId={9} />);

    expect(await screen.findByLabelText(/Sleeps/i)).toHaveValue(8);
    expect(screen.getByLabelText(/Bedrooms/i)).toHaveValue(4);
    expect(screen.queryByText(/Capacity not set/i)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("warns when guests is zero (the quote-search exclusion case)", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/9/capacity", () =>
        HttpResponse.json(makeCapacity({ guests: 0, bedrooms: 0, size_sqm: null })),
      ),
    );
    renderWithProviders(<CapacitySection propertyId={9} />);

    expect(await screen.findByText(/Capacity not set/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("disables save for non-reservations users", async () => {
    setReadonlyUser();
    server.use(http.get("/api/v1/properties/9/capacity", () => HttpResponse.json(makeCapacity())));
    renderWithProviders(<CapacitySection propertyId={9} />);

    expect(await screen.findByRole("button", { name: /save capacity/i })).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("PATCHes capacity on save and normalises a blank size to null", async () => {
    setReservationsUser();
    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties/9/capacity", () =>
        HttpResponse.json(makeCapacity({ size_sqm: null })),
      ),
      http.patch("/api/v1/properties/9/capacity", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeCapacity({ guests: 10, size_sqm: null }));
      }),
    );
    renderWithProviders(<CapacitySection propertyId={9} />);

    const guests = await screen.findByLabelText(/Sleeps/i);
    await userEvent.clear(guests);
    await userEvent.type(guests, "10");
    const save = screen.getByRole("button", { name: /save capacity/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    const body = lastPatchBody as unknown as Record<string, unknown>;
    expect(body.guests).toBe(10);
    expect(body.size_sqm).toBeNull();
    useAuthStore.getState().clear();
  });
});
