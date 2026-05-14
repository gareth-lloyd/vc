import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { SeasonFormDialog } from "../components/SeasonFormDialog";
import type { RatePlan } from "../schemas";

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

const eurCurrency = {
  id: 42,
  code: "EUR",
  name: "Euro",
  symbol: "€",
  decimal_places: 2,
  is_active: true,
};

const gbpCurrency = {
  id: 43,
  code: "GBP",
  name: "British Pound",
  symbol: "£",
  decimal_places: 2,
  is_active: true,
};

function installBaseHandlers(propertyCurrency: number | null = 42) {
  server.use(
    http.get("/api/v1/currencies", () => HttpResponse.json(drfPage([eurCurrency, gbpCurrency]))),
    http.get("/api/v1/properties/7/settings", () =>
      HttpResponse.json({
        property: 7,
        currency: propertyCurrency,
      }),
    ),
  );
}

describe("SeasonFormDialog — create", () => {
  it("posts to /properties/:id/seasons with the selected currency id", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/seasons", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 99,
            property: 7,
            name: postBody.name,
            currency: postBody.currency,
            price_basis: postBody.price_basis,
            effective_from: postBody.effective_from,
            effective_to: postBody.effective_to,
            is_active: postBody.is_active,
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <SeasonFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );

    const nameInput = await screen.findByLabelText(/^Name$/i);
    await userEvent.type(nameInput, "Summer 2027");
    await userEvent.type(screen.getByLabelText(/Effective from/i), "2027-06-01");
    await userEvent.type(screen.getByLabelText(/Effective to/i), "2027-09-30");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      name: "Summer 2027",
      currency: 42,
      price_basis: "gross",
      effective_from: "2027-06-01",
      effective_to: "2027-09-30",
    });
    useAuthStore.getState().clear();
  });

  it("defaults the currency picker from PropertySettings.currency", async () => {
    setReservationsUser();
    installBaseHandlers(43); // GBP
    renderWithProviders(
      <SeasonFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );
    const trigger = await screen.findByLabelText(/^Currency$/i);
    await waitFor(() => expect(within(trigger).getByText(/GBP/)).toBeInTheDocument());
    useAuthStore.getState().clear();
  });

  it("surfaces field errors from a 400 response", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    server.use(
      http.post("/api/v1/properties/7/seasons", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { name: ["This name is already taken."] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <SeasonFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Summer 2027");
    await userEvent.type(screen.getByLabelText(/Effective from/i), "2027-06-01");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/already taken/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});

describe("SeasonFormDialog — edit", () => {
  it("PATCHes the season with edited fields", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    const season: RatePlan = {
      id: 11,
      property: 7,
      name: "Summer 2026",
      currency: 42,
      price_basis: "gross",
      effective_from: "2026-06-01",
      effective_to: "2026-09-30",
      is_active: true,
      notes: "",
      inclusion: "",
    };
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/seasons/11", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...season, name: patchBody.name });
      }),
    );

    renderWithProviders(
      <SeasonFormDialog propertyId={7} open onOpenChange={() => {}} mode="edit" season={season} />,
    );

    const nameInput = (await screen.findByLabelText(/^Name$/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Summer 2026"));
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Summer 2026 (revised)");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.name).toBe("Summer 2026 (revised)");
    useAuthStore.getState().clear();
  });
});
