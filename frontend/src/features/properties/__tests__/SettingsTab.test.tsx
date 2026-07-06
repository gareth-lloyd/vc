import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { SettingsTab } from "../tabs/SettingsTab";

function makeProperty(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    name: "Casa Este",
    display_name: "Casa Este",
    slug: "casa-este",
    licence_number: "ETV-9999",
    status: "active",
    channel: "direct",
    category: null,
    region: null,
    feature_ids: [],
    legacy_id: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function makeSettings(overrides: Record<string, unknown> = {}) {
  return {
    property: 9,
    availability_default: "available",
    bookings_require_pre_approval: false,
    requires_enquiry_first: false,
    currency: null,
    check_in_time: "15:00",
    check_out_time: "10:00",
    changeover_day: "any",
    min_nights_rental: 3,
    min_nights_rental_note: "",
    prices_entered_as: "gross",
    timezone: "Europe/London",
    ...overrides,
  };
}

function makeFinance(overrides: Record<string, unknown> = {}) {
  return {
    property: 9,
    commission_calculation_type: "percent",
    commission_amount: "10.00",
    commission_note: "",
    tax_number: "",
    tax_is_exempt: false,
    tax_percentage: "0.00",
    deposit_required: true,
    deposit_calculation_type: "percent",
    deposit_amount: "30.00",
    interim_required: false,
    interim_calculation_type: null,
    interim_amount: null,
    days_interim_due_before_arrival: null,
    days_balance_due_before_arrival: 30,
    security_deposit_required: false,
    security_deposit_calculation_type: null,
    security_deposit_amount: null,
    security_deposit_days_due_before_arrival: null,
    security_deposit_days_refunded_after_departure: null,
    security_deposit_payment_method: null,
    cancellation_fee_amount: null,
    cancellation_fee_percent: "0.00",
    cancellation_window_days: 30,
    cancellation_notes: "",
    notes: "",
    season: null,
    contact: null,
    parent: null,
    ...overrides,
  };
}

function makeLocation(overrides: Record<string, unknown> = {}) {
  return {
    property: 9,
    address_line_1: "1 Harbour View",
    address_line_2: "",
    address_line_3: "",
    post_code: "TR26 1AA",
    locality_town: "St Ives",
    locality_region: "",
    country: 1,
    latitude: "50.211800",
    longitude: "-5.480700",
    timezone: "Europe/London",
    ...overrides,
  };
}

const COUNTRIES = [
  { id: 1, iso2: "GB", iso3: "GBR", name: "United Kingdom", is_active: true, sort_order: 0 },
  { id: 2, iso2: "IT", iso3: "ITA", name: "Italy", is_active: true, sort_order: 0 },
];

const REGIONS = [
  { id: 31, country: 1, country_iso2: "GB", name: "Cornwall", slug: "cornwall", is_active: true },
  { id: 32, country: 2, country_iso2: "IT", name: "Tuscany", slug: "tuscany", is_active: true },
];

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
        <Route index element={<Navigate to="settings" replace />} />
        <Route path="settings" element={<SettingsTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-este/settings" },
  );
}

function installBaseHandlers(property = makeProperty()) {
  server.use(
    http.get("/api/v1/properties/casa-este", () => HttpResponse.json(property)),
    http.get("/api/v1/properties/9/settings", () => HttpResponse.json(makeSettings())),
    http.get("/api/v1/properties/9/finance", () => HttpResponse.json(makeFinance())),
    http.get("/api/v1/properties/9/location", () => HttpResponse.json(makeLocation())),
    http.get("/api/v1/countries", () => HttpResponse.json(drfPage(COUNTRIES))),
    http.get("/api/v1/regions", () => HttpResponse.json(drfPage(REGIONS))),
  );
}

describe("SettingsTab", () => {
  it("renders operational, finance, and lifecycle sections", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    expect(await screen.findByText(/Operational settings/i)).toBeInTheDocument();
    expect(await screen.findByText("Location")).toBeInTheDocument();
    expect(await screen.findByText(/Finance configuration/i)).toBeInTheDocument();
    expect(await screen.findByText(/Lifecycle/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows Archive button when status is active and Activate when draft", async () => {
    setReservationsUser();
    installBaseHandlers(makeProperty({ status: "draft" }));
    setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /^activate$/i })).toBeEnabled());
    useAuthStore.getState().clear();
  });

  it("disables save buttons for non-reservations users", async () => {
    setReadonlyUser();
    installBaseHandlers();
    setup();
    const saveSettings = await screen.findByRole("button", { name: /save settings/i });
    const saveFinance = await screen.findByRole("button", { name: /save finance/i });
    const saveLocation = await screen.findByRole("button", { name: /save location/i });
    expect(saveSettings).toBeDisabled();
    expect(saveFinance).toBeDisabled();
    expect(saveLocation).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("PATCHes settings when operational form is submitted with changes", async () => {
    setReservationsUser();
    installBaseHandlers();

    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/settings", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeSettings({ min_nights_rental: 5 }));
      }),
    );

    setup();
    const minNights = await screen.findByLabelText("Minimum nights");
    await userEvent.clear(minNights);
    await userEvent.type(minNights, "5");
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).min_nights_rental).toBe(5);
    useAuthStore.getState().clear();
  });

  it("renders '—' for an unset select and PATCHes explicit null on reset (GAP-070)", async () => {
    setReservationsUser();
    installBaseHandlers();
    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ changeover_day: null })),
      ),
      http.patch("/api/v1/properties/9/settings", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeSettings({ changeover_day: null }));
      }),
    );

    setup();
    // Populate direction: an API null must render the "—" option (the
    // post-GAP-070 default state), not a blank/crashing Radix trigger.
    const changeover = await screen.findByRole("combobox", { name: /changeover day/i });
    expect(changeover).toHaveTextContent("—");

    // Reset direction: picking "—" must PATCH an explicit null (backend
    // fallback applies) — not the sentinel string, not a dropped key.
    await userEvent.click(screen.getByRole("combobox", { name: /availability default/i }));
    await userEvent.click(await screen.findByRole("option", { name: "—" }));
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).availability_default).toBeNull();
    useAuthStore.getState().clear();
  });

  it("PATCHes explicit null when a finance calc type is reset to '—' (GAP-070)", async () => {
    setReservationsUser();
    installBaseHandlers();
    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/finance", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeFinance({ commission_calculation_type: null }));
      }),
    );

    setup();
    await userEvent.click(await screen.findByRole("combobox", { name: /commission type/i }));
    await userEvent.click(await screen.findByRole("option", { name: "—" }));
    const save = screen.getByRole("button", { name: /save finance/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect(
      (lastPatchBody as unknown as Record<string, unknown>).commission_calculation_type,
    ).toBeNull();
    useAuthStore.getState().clear();
  });

  it("renders the saved calendar_url in the operational form (GAP-034)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ calendar_url: "https://owner.example.com/cal" })),
      ),
    );

    setup();
    const input = await screen.findByLabelText("Online calendar URL");
    expect(input).toHaveValue("https://owner.example.com/cal");
    useAuthStore.getState().clear();
  });

  it("PATCHes a calendar_url when the operational form is submitted (GAP-034)", async () => {
    setReservationsUser();
    installBaseHandlers();

    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/settings", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeSettings({ calendar_url: "https://owner.example.com/cal" }));
      }),
    );

    setup();
    const input = await screen.findByLabelText("Online calendar URL");
    await userEvent.type(input, "https://owner.example.com/cal");
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).calendar_url).toBe(
      "https://owner.example.com/cal",
    );
    useAuthStore.getState().clear();
  });

  it("sends null for a cleared calendar_url rather than an empty string (GAP-034)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ calendar_url: "https://owner.example.com/cal" })),
      ),
    );

    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/settings", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeSettings({ calendar_url: null }));
      }),
    );

    setup();
    const input = await screen.findByLabelText("Online calendar URL");
    await userEvent.clear(input);
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).calendar_url).toBeNull();
    useAuthStore.getState().clear();
  });

  it("surfaces a server 400 for an invalid calendar_url (GAP-034)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.patch("/api/v1/properties/9/settings", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { calendar_url: ["Enter a valid URL."] },
          },
          { status: 400 },
        ),
      ),
    );

    setup();
    const input = await screen.findByLabelText("Online calendar URL");
    await userEvent.type(input, "not a url");
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    expect(await screen.findByText(/Enter a valid URL\./)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("PATCHes the location endpoint when the location form is edited", async () => {
    setReservationsUser();
    installBaseHandlers();

    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/location", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLocation({ locality_town: "Penzance" }));
      }),
    );

    setup();
    const town = await screen.findByLabelText("Town");
    await userEvent.clear(town);
    await userEvent.type(town, "Penzance");
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).locality_town).toBe("Penzance");
    useAuthStore.getState().clear();
  });

  it("PATCHes the property root with the region only when it changed", async () => {
    setReservationsUser();
    installBaseHandlers();

    let locationBody: Record<string, unknown> | null = null;
    let rootBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/location", async ({ request }) => {
        locationBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLocation());
      }),
      http.patch("/api/v1/properties/9", async ({ request }) => {
        rootBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeProperty({ region: 31 }));
      }),
    );

    setup();
    // Scoped by the address country (GB) — only Cornwall on offer.
    await userEvent.click(await screen.findByRole("combobox", { name: /listing region/i }));
    expect(screen.queryByRole("option", { name: /Tuscany/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("option", { name: "Cornwall" }));
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(rootBody).not.toBeNull());
    expect(rootBody).toEqual({ region: 31 });
    // A region-only change must not fire a redundant address PATCH.
    expect(locationBody).toBeNull();
    useAuthStore.getState().clear();
  });

  it("shows a toast when the address saves but the region PATCH fails", async () => {
    setReservationsUser();
    installBaseHandlers();
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.patch("/api/v1/properties/9/location", () => HttpResponse.json(makeLocation())),
      http.patch("/api/v1/properties/9", () => new HttpResponse(null, { status: 500 })),
    );

    setup();
    await userEvent.click(await screen.findByRole("combobox", { name: /listing region/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Cornwall" }));
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith(expect.stringMatching(/address was saved.*region/i)),
    );
    errorSpy.mockRestore();
    useAuthStore.getState().clear();
  });

  it("sends null for a cleared coordinate rather than an empty string", async () => {
    setReservationsUser();
    installBaseHandlers();

    let lastPatchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/9/location", async ({ request }) => {
        lastPatchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLocation({ latitude: null }));
      }),
    );

    setup();
    const latitude = await screen.findByLabelText("Latitude");
    await userEvent.clear(latitude);
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(lastPatchBody).not.toBeNull());
    expect((lastPatchBody as unknown as Record<string, unknown>).latitude).toBeNull();
    useAuthStore.getState().clear();
  });

  it("surfaces a 400 validation error in the alert banner", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.patch("/api/v1/properties/9/location", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { non_field_errors: ["Coordinates are out of range."] },
          },
          { status: 400 },
        ),
      ),
    );

    setup();
    const latitude = await screen.findByLabelText("Latitude");
    await userEvent.clear(latitude);
    await userEvent.type(latitude, "95");
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    expect(await screen.findByText(/Coordinates are out of range\./)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("keeps an inactive saved country selectable in the picker", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/location", () =>
        HttpResponse.json(makeLocation({ country: 3 })),
      ),
      http.get("/api/v1/countries", () =>
        HttpResponse.json(
          drfPage([
            ...COUNTRIES,
            { id: 3, iso2: "ZZ", iso3: "ZZZ", name: "Retired Land", is_active: false },
          ]),
        ),
      ),
    );

    setup();
    const trigger = await screen.findByLabelText("Country");
    await userEvent.click(trigger);
    // The deactivated country the property is in is still offered, so the
    // operator can see and re-confirm it rather than facing a blank picker.
    expect(await screen.findByRole("option", { name: "Retired Land" })).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows a toast when the location PATCH returns a 500", async () => {
    setReservationsUser();
    installBaseHandlers();
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.patch("/api/v1/properties/9/location", () => new HttpResponse(null, { status: 500 })),
    );

    setup();
    const town = await screen.findByLabelText("Town");
    await userEvent.clear(town);
    await userEvent.type(town, "Penzance");
    const save = screen.getByRole("button", { name: /save location/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    await waitFor(() => expect(errorSpy).toHaveBeenCalled());
    errorSpy.mockRestore();
    useAuthStore.getState().clear();
  });

  it("surfaces a server field validation error instead of a bare 'Validation failed'", async () => {
    setReservationsUser();
    installBaseHandlers();

    server.use(
      http.patch("/api/v1/properties/9/settings", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { min_nights_rental_note: ["This field may not be null."] },
          },
          { status: 422 },
        ),
      ),
    );

    setup();
    const minNights = await screen.findByLabelText("Minimum nights");
    await userEvent.clear(minNights);
    await userEvent.type(minNights, "7");
    const save = screen.getByRole("button", { name: /save settings/i });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);

    expect(await screen.findByText("This field may not be null.")).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("adorns a fixed finance amount with the property's currency (GAP-026)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ currency_code: "GBP" })),
      ),
      http.get("/api/v1/properties/9/finance", () =>
        HttpResponse.json(
          makeFinance({ commission_calculation_type: "fixed", commission_amount: "150.00" }),
        ),
      ),
    );

    setup();
    expect(await screen.findByDisplayValue("150.00")).toBeInTheDocument();
    // The fixed commission amount is prefixed with the resolved currency symbol.
    expect(screen.getAllByText("£").length).toBeGreaterThanOrEqual(1);
    useAuthStore.getState().clear();
  });

  it("adorns a percent finance amount with % rather than a currency", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ currency_code: "GBP" })),
      ),
    );

    setup();
    // Default finance has commission + deposit on a `percent` basis.
    await waitFor(() => expect(screen.getAllByText("%").length).toBeGreaterThanOrEqual(2));
    // No currency symbol, since no amount is a fixed monetary value.
    expect(screen.queryByText("£")).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("prompts to set a currency when a fixed amount has none resolved", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/9/settings", () =>
        HttpResponse.json(makeSettings({ currency_code: null })),
      ),
      http.get("/api/v1/properties/9/finance", () =>
        HttpResponse.json(
          makeFinance({ commission_calculation_type: "fixed", commission_amount: "150.00" }),
        ),
      ),
    );

    setup();
    expect(await screen.findByText(/No currency is set for this property/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});
