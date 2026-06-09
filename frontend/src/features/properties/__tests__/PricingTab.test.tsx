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

const seasonDetailCard = {
  id: 100,
  plan: 11,
  name: "Standard",
  description: "Default card",
  min_nights: 7,
  max_nights: 30,
  is_active: true,
  rules: [
    {
      id: 200,
      card: 100,
      date_from: "2026-06-01",
      date_to: "2026-07-31",
      min_party: 2,
      max_party: 8,
      nightly: "350.00",
      weekly: "2100.00",
      is_poa: false,
    },
  ],
};

// Seasons list + drill-down detail with one card and one rule. `cards` lets a
// test vary the detail response across refetches (e.g. after a delete).
function installSeasonDetailHandlers(cards?: () => unknown[] | undefined) {
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
        cards: cards?.() ?? [seasonDetailCard],
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

  it("drills into a season to show rate cards and rules, then navigates back", async () => {
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
          cards: [
            {
              id: 100,
              plan: 11,
              name: "Standard",
              description: "Default card",
              min_nights: 7,
              max_nights: 30,
              is_active: true,
              rules: [
                {
                  id: 200,
                  card: 100,
                  date_from: "2026-06-01",
                  date_to: "2026-07-31",
                  min_party: 2,
                  max_party: 8,
                  nightly: "350.00",
                  weekly: "2100.00",
                  is_poa: false,
                },
              ],
            },
          ],
        }),
      ),
    );

    const user = userEvent.setup();
    setup();

    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    expect(await screen.findByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("Default card")).toBeInTheDocument();
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

  it("hides card and rule write controls without the RESERVATIONS role", async () => {
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    expect(screen.getByRole("button", { name: /add rate card/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /card actions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rule actions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add rule/i })).not.toBeInTheDocument();
  });

  it("opens the card dialogs from the Add button and row menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /add rate card/i }));
    expect(await screen.findByRole("heading", { name: /add rate card/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    await user.click(screen.getByRole("button", { name: /card actions/i }));
    await user.click(await screen.findByText(/^Edit$/i));
    expect(await screen.findByRole("heading", { name: /edit rate card/i })).toBeInTheDocument();
    expect((screen.getByLabelText(/^Name$/i) as HTMLInputElement).value).toBe("Standard");
    useAuthStore.getState().clear();
  });

  it("seeds the Add rule dialog from the card's last rule", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /add rule/i }));
    expect(await screen.findByRole("heading", { name: /add rule/i })).toBeInTheDocument();
    expect((screen.getByLabelText(/^From$/i) as HTMLInputElement).value).toBe("2026-08-01");
    expect((screen.getByLabelText(/Maximum party/i) as HTMLInputElement).value).toBe("8");
    useAuthStore.getState().clear();
  });

  it("deletes a rate card via the row menu and re-renders the season", async () => {
    setReservationsUser();
    installBaseHandlers();
    let cardDeleted = false;
    installSeasonDetailHandlers(() => (cardDeleted ? [] : undefined));
    server.use(
      http.delete("/api/v1/rate-cards/100", () => {
        cardDeleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /card actions/i }));
    await user.click(await screen.findByText(/^Delete$/i));
    await user.click(await screen.findByRole("button", { name: /^Remove$/i }));
    expect(await screen.findByText(/No rate cards/i)).toBeInTheDocument();
    expect(cardDeleted).toBe(true);
    useAuthStore.getState().clear();
  });

  it("duplicates a rate card via the row menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();
    let duplicateCalled = false;
    server.use(
      http.post("/api/v1/rate-cards/100:duplicate", () => {
        duplicateCalled = true;
        return HttpResponse.json(
          { ...seasonDetailCard, id: 101, name: "Standard (copy)" },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: /Summer 2026/i }));
    await screen.findByText("Standard");

    await user.click(screen.getByRole("button", { name: /card actions/i }));
    await user.click(await screen.findByText(/^Duplicate$/i));
    await user.click(await screen.findByRole("button", { name: /^Duplicate$/i }));
    await waitFor(() => expect(duplicateCalled).toBe(true));
    useAuthStore.getState().clear();
  });

  it("deletes a rule via the rule row menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    installSeasonDetailHandlers();
    let ruleDeleted = false;
    server.use(
      http.delete("/api/v1/rules/200", () => {
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
