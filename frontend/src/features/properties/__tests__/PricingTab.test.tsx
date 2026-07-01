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
import { PricingTab } from "../tabs/PricingTab";

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

const propertyFixture = {
  id: 5,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
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

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)));
}

// GAP-056: a rate period owns the dates + nights; its bands (rules) are party ×
// price only, and carry a `period` FK — never `card`/dates.
const seasonDetailPeriod = {
  id: 100,
  plan: 11,
  name: "Standard",
  date_from: "2026-06-01",
  date_to: "2026-07-31",
  min_nights: 7,
  max_nights: 30,
  is_active: true,
  coverage_gaps: [],
  bands: [
    {
      id: 200,
      period: 100,
      min_party: 2,
      max_party: 8,
      nightly: "350.00",
      weekly: "2100.00",
      is_poa: false,
    },
  ],
};

// Seasons list + drill-down detail with one period and one band. `periods` lets a
// test vary the detail response across refetches (e.g. after a delete).
function installSeasonDetailHandlers(periods?: () => unknown[] | undefined) {
  server.use(
    http.get("/api/v1/properties/5/seasons", () =>
      HttpResponse.json(
        drfPage([
          {
            id: 11,
            property: 5,
            name: "Summer 2026",
            currency: 42,
            price_basis: "gross",
            effective_from: "2026-06-01",
            effective_to: "2026-09-30",
            is_active: true,
          },
        ]),
      ),
    ),
    http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
    http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    http.get("/api/v1/seasons/11", () =>
      HttpResponse.json({
        id: 11,
        property: 5,
        name: "Summer 2026",
        currency: 42,
        price_basis: "gross",
        effective_from: "2026-06-01",
        effective_to: "2026-09-30",
        is_active: true,
        periods: periods?.() ?? [seasonDetailPeriod],
      }),
    ),
  );
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="pricing" replace />} />
        <Route path="pricing" element={<PricingTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-norte/pricing" },
  );
}

describe("PricingTab", () => {
  it("renders seasons, extras and discounts", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 11,
              property: 5,
              name: "Summer 2026",
              currency: 42,
              price_basis: "gross",
              effective_from: "2026-06-01",
              effective_to: "2026-09-30",
              is_active: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/extras", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 21,
              property: 5,
              name: "Cleaning fee",
              kind: "service",
              calc: "flat",
              amount: "120.00",
              currency: 42,
              currency_code: "EUR",
              is_mandatory: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/discounts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 31,
              property: 5,
              name: "Early bird",
              code: "EARLY10",
              kind: "percent",
              amount: "10.00",
              rule_kind: "code",
              valid_from: "2026-01-01",
              valid_to: "2026-04-30",
              is_active: true,
            },
          ]),
        ),
      ),
    );

    setup();

    expect(await screen.findByText("Summer 2026")).toBeInTheDocument();
    expect(await screen.findByText("Cleaning fee")).toBeInTheDocument();
    expect(await screen.findByText("Early bird")).toBeInTheDocument();
    expect(screen.getByText("EARLY10")).toBeInTheDocument();
  });

  it("drills into a season to show rate periods and bands, then navigates back", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 11,
              property: 5,
              name: "Summer 2026",
              currency: 42,
              price_basis: "gross",
              effective_from: "2026-06-01",
              effective_to: "2026-09-30",
              is_active: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/seasons/11", () =>
        HttpResponse.json({
          id: 11,
          property: 5,
          name: "Summer 2026",
          currency: 42,
          price_basis: "gross",
          effective_from: "2026-06-01",
          effective_to: "2026-09-30",
          is_active: true,
          periods: [seasonDetailPeriod],
        }),
      ),
    );

    const user = userEvent.setup();
    setup();

    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    expect(await screen.findByText("Standard")).toBeInTheDocument();
    expect(screen.getByText(/Nights 7–30/i)).toBeInTheDocument();
    expect(screen.getByText("350.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Back to seasons/i }));
    await waitFor(() => expect(screen.queryByText("Standard")).not.toBeInTheDocument());
    expect(screen.getByText("Summer 2026")).toBeInTheDocument();
  });

  it("renders empty states when there are no seasons, extras, or discounts", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    );

    setup();

    expect(await screen.findByText(/No seasons defined/i)).toBeInTheDocument();
    expect(await screen.findByText(/No extras/i)).toBeInTheDocument();
    expect(await screen.findByText(/No discounts/i)).toBeInTheDocument();
  });

  it("disables Add season when the user lacks the RESERVATIONS role", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    );
    setup();
    const btn = await screen.findByRole("button", { name: /add season/i });
    expect(btn).toBeDisabled();
  });

  it("deletes a season via the row menu and confirm dialog", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 11,
              property: 5,
              name: "Summer 2026",
              currency: 42,
              price_basis: "gross",
              effective_from: "2026-06-01",
              effective_to: "2026-09-30",
              is_active: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    );
    let deleteCalled = false;
    server.use(
      http.delete("/api/v1/seasons/11", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    setup();
    await waitFor(() => expect(screen.getByText("Summer 2026")).toBeInTheDocument());
    const menu = await screen.findByRole("button", { name: /actions/i });
    await userEvent.click(menu);
    await userEvent.click(await screen.findByText(/^Delete$/i));
    await userEvent.click(await screen.findByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(deleteCalled).toBe(true));
    useAuthStore.getState().clear();
  });

  it("duplicates a season via the row menu and confirm dialog", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 11,
              property: 5,
              name: "Summer 2026",
              currency: 42,
              price_basis: "gross",
              effective_from: "2026-06-01",
              effective_to: "2026-09-30",
              is_active: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    );
    let duplicateCalled = false;
    server.use(
      http.post("/api/v1/seasons/11:duplicate", () => {
        duplicateCalled = true;
        return HttpResponse.json(
          {
            id: 12,
            property: 5,
            name: "Summer 2026 (copy)",
            currency: 42,
            price_basis: "gross",
            effective_from: "2026-06-01",
            effective_to: "2026-09-30",
            is_active: true,
          },
          { status: 201 },
        );
      }),
    );

    setup();
    await waitFor(() => expect(screen.getByText("Summer 2026")).toBeInTheDocument());
    const menu = await screen.findByRole("button", { name: /actions/i });
    await userEvent.click(menu);
    await userEvent.click(await screen.findByText(/^Duplicate$/i));
    await userEvent.click(await screen.findByRole("button", { name: /^Duplicate$/i }));
    await waitFor(() => expect(duplicateCalled).toBe(true));
    useAuthStore.getState().clear();
  });

  it("hides period and band write controls without the RESERVATIONS role", async () => {
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    expect(screen.getByRole("button", { name: /add rate period/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /period actions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rule actions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add rule/i })).not.toBeInTheDocument();
  });

  it("opens the rate-period dialogs from the Add button and row menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /add rate period/i }));
    expect(await screen.findByRole("heading", { name: /add rate period/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    await user.click(screen.getByRole("button", { name: /period actions/i }));
    await user.click(await screen.findByText(/^Edit$/i));
    expect(await screen.findByRole("heading", { name: /edit rate period/i })).toBeInTheDocument();
    expect((screen.getByLabelText(/Name/i) as HTMLInputElement).value).toBe("Standard");
    useAuthStore.getState().clear();
  });

  it("opens the Add rule dialog for a period defaulting party to 1", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /add rule/i }));
    expect(await screen.findByRole("heading", { name: /add rule/i })).toBeInTheDocument();
    // Bands are party × price only now (no dates); a fresh band defaults to 1–1.
    expect((screen.getByLabelText(/Minimum party/i) as HTMLInputElement).value).toBe("1");
    expect((screen.getByLabelText(/Maximum party/i) as HTMLInputElement).value).toBe("1");
    useAuthStore.getState().clear();
  });

  it("deletes a rate period via the row menu and re-renders the season", async () => {
    setReservationsUser();
    installBaseHandlers();
    let periodDeleted = false;
    installSeasonDetailHandlers(() => (periodDeleted ? [] : undefined));
    server.use(
      http.delete("/api/v1/periods/100", () => {
        periodDeleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /period actions/i }));
    await user.click(await screen.findByText(/^Delete$/i));
    await user.click(await screen.findByRole("button", { name: /^Remove$/i }));
    expect(await screen.findByText(/No rate periods/i)).toBeInTheDocument();
    expect(periodDeleted).toBe(true);
    useAuthStore.getState().clear();
  });

  it("deletes a rule via the rule row menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();
    let ruleDeleted = false;
    server.use(
      http.delete("/api/v1/bands/200", () => {
        ruleDeleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /rule actions/i }));
    await user.click(await screen.findByText(/^Delete$/i));
    await user.click(await screen.findByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(ruleDeleted).toBe(true));
    useAuthStore.getState().clear();
  });

  it("renders an error state for a failing section while other sections still render", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/seasons", () => HttpResponse.json({}, { status: 500 })),
      http.get("/api/v1/properties/5/extras", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 21,
              property: 5,
              name: "Cleaning fee",
              kind: "service",
              calc: "flat",
              amount: "120.00",
              currency: 42,
              currency_code: "EUR",
              is_mandatory: true,
            },
          ]),
        ),
      ),
      http.get("/api/v1/properties/5/discounts", () => HttpResponse.json(drfPage([]))),
    );

    setup();

    expect(await screen.findByText(/Couldn't load seasons/i)).toBeInTheDocument();
    expect(await screen.findByText("Cleaning fee")).toBeInTheDocument();
  });
});
