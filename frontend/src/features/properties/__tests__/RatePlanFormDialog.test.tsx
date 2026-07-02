import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
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

// The picker's popover inputs reuse the existing field labels.
const SEASON_DATE_LABELS = { from: /^effective from$/i, to: /^effective to$/i };

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
  it("posts to /properties/:id/rate-plans with the selected currency id", async () => {
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
            effective_from: postBody.effective_from,
            effective_to: postBody.effective_to,
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
    await userEvent.type(nameInput, "Summer 2027");
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(
      userEvent,
      picker,
      { from: "2027-06-01", to: "2027-09-30" },
      SEASON_DATE_LABELS,
    );
    expectTriggerRange(/^dates/i, "1 Jun – 30 Sep 2027 · 122 days");
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
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(userEvent, picker, { from: "2027-06-01" }, SEASON_DATE_LABELS);
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
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(userEvent, picker, { from: "2027-06-01" }, SEASON_DATE_LABELS);
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
    effective_from: "2026-06-01",
    effective_to: "2026-09-30",
    is_active: true,
    notes: "",
  };

  it("PATCHes the season with edited fields", async () => {
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
    // The stored season window prefills the picker trigger.
    expectTriggerRange(/^dates/i, "1 Jun – 30 Sep 2026 · 122 days");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Summer 2026 (revised)");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.name).toBe("Summer 2026 (revised)");
    useAuthStore.getState().clear();
  });

  it("supports an open-ended season: cleared To shows partial trigger text and PATCHes explicit null", async () => {
    setReservationsUser();
    installBaseHandlers(42);
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/rate-plans/11", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...season, effective_from: "2026-07-04", effective_to: null });
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

    // Open end via the popover's typed inputs: retype From, clear To (a
    // calendar click always writes a closed 1-day range in days mode).
    const picker = await openDateRange(userEvent, /^dates/i);
    await waitFor(() =>
      expect(picker.getByLabelText(SEASON_DATE_LABELS.from)).toHaveValue("2026-06-01"),
    );
    await typeDateRange(userEvent, picker, { from: "2026-07-04", to: "" }, SEASON_DATE_LABELS);

    // From-only partial text — no day count, no dangling end.
    expectTriggerRange(/^dates/i, "4 Jul 2026 – …");
    expect(screen.getByRole("button", { name: /^dates/i })).not.toHaveTextContent("days");

    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    // The submit mapping sends explicit `null` for an empty To (never "" or
    // an omitted key) so the PATCH actually clears a previously-set end date.
    expect(patchBody!.effective_from).toBe("2026-07-04");
    expect(patchBody!.effective_to).toBeNull();
    useAuthStore.getState().clear();
  });
});
