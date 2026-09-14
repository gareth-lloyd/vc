import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { RatePlanFormDialog } from "../components/RatePlanFormDialog";
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

describe("RatePlanFormDialog — create", () => {
  it("posts to /properties/:id/rate-plans with the selected currency id and no dates", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/rate-plans", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 99,
            property: 7,
            name: postBody.name,
            currency: postBody.currency,
            price_basis: postBody.price_basis,
            is_active: postBody.is_active,
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <RatePlanFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );

    const nameInput = await screen.findByLabelText(/^Name$/i);
    // GAP-110: a rate plan is a date-less regime bucket — RatePeriod rows are
    // the only date authority, so the dialog offers no effective window.
    expect(screen.queryByLabelText(/effective/i)).toBeNull();
    expect(screen.queryByLabelText(/dates/i)).toBeNull();
    await userEvent.type(nameInput, "Summer 2027");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      name: "Summer 2027",
      currency: 42,
      price_basis: "gross",
    });
    expect(postBody).not.toHaveProperty("effective_from");
    expect(postBody).not.toHaveProperty("effective_to");
    useAuthStore.getState().clear();
  });

  it("defaults the currency picker from PropertySettings.currency", async () => {
    setReservationsUser();
    installBaseHandlers(43); // GBP
    renderWithProviders(
      <RatePlanFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );
    const trigger = await screen.findByLabelText(/^Currency$/i);
    await waitFor(() => expect(within(trigger).getByText(/GBP/)).toBeInTheDocument());
    useAuthStore.getState().clear();
  });

  it("defaults price_basis from the property's prices_entered_as (GAP-035)", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/currencies", () => HttpResponse.json(drfPage([eurCurrency, gbpCurrency]))),
      http.get("/api/v1/properties/7/settings", () =>
        HttpResponse.json({ property: 7, currency: 42, prices_entered_as_effective: "net" }),
      ),
    );
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/rate-plans", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 99, property: 7, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePlanFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );
    // The basis select reflects the property default before any edit.
    const basisTrigger = await screen.findByLabelText(/Price basis/i);
    await waitFor(() => expect(within(basisTrigger).getByText(/^Net$/i)).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText(/^Name$/i), "Agent net 2027");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ price_basis: "net" });
    useAuthStore.getState().clear();
  });

  it("surfaces field errors from a 400 response", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    server.use(
      http.post("/api/v1/properties/7/rate-plans", () =>
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
      <RatePlanFormDialog propertyId={7} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Summer 2027");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/already taken/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});

describe("RatePlanFormDialog — edit", () => {
  const season: RatePlan = {
    id: 11,
    property: 7,
    name: "Summer 2026",
    currency: 42,
    price_basis: "gross",
    is_active: true,
    notes: "",
  };

  it("PATCHes the season with edited fields and no dates", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/rate-plans/11", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...season, name: patchBody.name });
      }),
    );

    renderWithProviders(
      <RatePlanFormDialog
        propertyId={7}
        open
        onOpenChange={() => {}}
        mode="edit"
        season={season}
      />,
    );

    const nameInput = (await screen.findByLabelText(/^Name$/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Summer 2026"));
    expect(screen.queryByLabelText(/effective/i)).toBeNull();
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Summer 2026 (revised)");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.name).toBe("Summer 2026 (revised)");
    expect(patchBody).not.toHaveProperty("effective_from");
    expect(patchBody).not.toHaveProperty("effective_to");
    useAuthStore.getState().clear();
  });
});
