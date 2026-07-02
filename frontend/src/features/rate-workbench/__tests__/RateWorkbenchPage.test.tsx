import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it, afterEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "@/features/properties/PropertyDetailLayout";
import { RateWorkbenchPage } from "../RateWorkbenchPage";

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

const season = {
  id: 100,
  property: 7,
  name: "Summer 2026",
  currency_code: "EUR",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
  is_active: true,
};

const ratePlanDetail = {
  ...season,
  periods: [
    {
      id: 500,
      plan: 100,
      name: "Standard",
      date_from: "2026-06-01",
      date_to: "2026-06-28",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 1, period: 500, min_party: 1, max_party: 8, nightly: "650" }],
    },
    {
      id: 501,
      plan: 100,
      name: "Peak",
      date_from: "2026-06-29",
      date_to: "2026-08-31",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 2, period: 501, min_party: 1, max_party: 8, nightly: "900" }],
    },
  ],
};

const service = {
  id: 9,
  property: 7,
  name: "Daily maid",
  copy: "Included",
  sort_order: 0,
  is_active: true,
};
const extra = {
  id: 11,
  property: 7,
  name: "Airport transfer",
  amount: "120",
  currency_code: "EUR",
};
const discount = { id: 21, property: 7, name: "Early bird", code: "EARLY", amount: "10" };
const changeover = {
  id: 31,
  property: 7,
  weekday: "sat",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
};

function installHandlers() {
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([season]))),
    http.get("/api/v1/rate-plans/100", () => HttpResponse.json(ratePlanDetail)),
    http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([service]))),
    http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([extra]))),
    http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([discount]))),
    http.get("/api/v1/properties/7/change-over-rules", () =>
      HttpResponse.json(drfPage([changeover])),
    ),
  );
}

function setUser(role: string, is_staff = true) {
  useAuthStore.getState().setMe(
    {
      id: 1,
      email: "a@test.com",
      first_name: "A",
      last_name: "T",
      is_active: true,
      is_staff,
      is_superuser: false,
      preferred_language: "en",
      role,
    },
    { role, is_superuser: false, permissions: [] },
  );
}

function setup(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<div>details tab</div>} />
        <Route path="rate-workbench" element={<RateWorkbenchPage />} />
      </Route>
    </Routes>,
    { route },
  );
}

afterEach(() => useAuthStore.getState().clear());

describe("RateWorkbenchPage", () => {
  it("renders the timeline lanes with bands for the reservations role", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    expect(await screen.findByRole("heading", { name: "Rates" })).toBeInTheDocument();
    // Bands render (once data loads) as buttons with descriptive aria labels
    // (no in-band text). Awaiting one confirms the timeline mounted.
    expect(await screen.findByRole("button", { name: /Standard, 1 Jun 2026/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Airport transfer/ })).toBeInTheDocument();
    // Lane labels — the redundant per-currency "Seasons" (rate-plan) lane is gone;
    // the timeline now leads with the rate-periods lane.
    expect(screen.queryByText("Seasons")).not.toBeInTheDocument();
    expect(screen.getByText("Rate periods")).toBeInTheDocument();
    expect(screen.getByText("Changeover")).toBeInTheDocument();
  });

  it("shows the Rates tab in nav to a read-only user (GAP-060 dropped the writer-only gate)", async () => {
    // The old Pricing tab had no visibility gate; when the Rates tab absorbed it,
    // the workbench's writer-only nav gate was dropped so viewers keep read-only
    // rate visibility (its write affordances stay role-gated inline).
    setUser("readonly", false);
    installHandlers();
    setup("/properties/casa-sur/details");
    expect(await screen.findByText("details tab")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Rates" })).toBeInTheDocument();
  });

  it("shows the empty state when the property has no configuration", async () => {
    setUser("reservations");
    server.use(
      http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    setup("/properties/casa-sur/rate-workbench");
    expect(await screen.findByText(/No configuration yet/i)).toBeInTheDocument();
  });

  it("distinguishes config in another year from no config at all", async () => {
    setUser("reservations");
    // A season configured only for 2025; the page defaults to the current year
    // (2026) so no bands are visible — but the property IS configured.
    const pastSeason = { ...season, effective_from: "2025-06-01", effective_to: "2025-08-31" };
    server.use(
      http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([pastSeason]))),
      http.get("/api/v1/rate-plans/100", () => HttpResponse.json({ ...pastSeason, periods: [] })),
      http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    setup("/properties/casa-sur/rate-workbench");
    expect(await screen.findByText(/Nothing scheduled in 2026/i)).toBeInTheDocument();
    expect(screen.queryByText(/No configuration yet/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Period creation from the workbench (Unit 3): the season selector must list
// ALL plans (a zero-period plan is exactly the one you need to add periods
// to), and the matrix header offers "Add period" prefilled after the latest
// existing period.
// ---------------------------------------------------------------------------

const winterSeason = {
  id: 101,
  property: 7,
  name: "Winter 2026",
  currency_code: "EUR",
  effective_from: "2026-11-01",
  effective_to: "2027-02-28",
  is_active: true,
};

function installMultiSeasonHandlers() {
  installHandlers();
  // Second, zero-period season on top of the shared single-season handlers.
  server.use(
    http.get("/api/v1/properties/7/rate-plans", () =>
      HttpResponse.json(drfPage([season, winterSeason])),
    ),
    http.get("/api/v1/rate-plans/101", () => HttpResponse.json({ ...winterSeason, periods: [] })),
  );
}

describe("RateWorkbenchPage — period create", () => {
  it("lists a zero-period season in the selector and shows its Add period empty state", async () => {
    setUser("reservations");
    installMultiSeasonHandlers();
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    const picker = await screen.findByRole("combobox", { name: "Choose a season" });
    await user.click(picker);
    // Option labels carry the plan's currency (a plan == a currency).
    await user.click(await screen.findByRole("option", { name: /Winter 2026/ }));

    expect(await screen.findByText("This season has no rate periods yet.")).toBeInTheDocument();
    // Both the header button and the empty-state CTA offer period creation.
    expect(screen.getAllByRole("button", { name: "Add period" }).length).toBeGreaterThanOrEqual(1);
  });

  it("opens the period dialog prefilled with the day after the latest period and creates", async () => {
    setUser("reservations");
    installMultiSeasonHandlers();
    let created = false;
    const posted: Array<Record<string, unknown>> = [];
    const autumnPeriod = {
      id: 502,
      plan: 100,
      name: "Autumn",
      date_from: "2026-09-01",
      date_to: "2026-09-30",
      is_active: true,
      coverage_gaps: [],
      bands: [],
    };
    server.use(
      http.post("/api/v1/rate-plans/100/rate-periods", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        created = true;
        return HttpResponse.json(autumnPeriod, { status: 201 });
      }),
      http.get("/api/v1/rate-plans/100", () =>
        HttpResponse.json(
          created
            ? { ...ratePlanDetail, periods: [...ratePlanDetail.periods, autumnPeriod] }
            : ratePlanDetail,
        ),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    // Summer 2026 (the plan with periods) is the default selection.
    await user.click(await screen.findByRole("button", { name: "Add period" }));
    const dialog = await screen.findByRole("dialog");
    // Latest period ends 2026-08-31 → prefill starts the day after (open end).
    expectTriggerRange(/^dates/i, "1 Sep 2026 – …");
    await user.type(within(dialog).getByLabelText(/Name/i), "Autumn");
    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { to: "2026-09-30" });
    await user.click(within(dialog).getByRole("button", { name: /Save/i }));

    await screen.findByText("Autumn", { exact: false });
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({
      name: "Autumn",
      date_from: "2026-09-01",
      date_to: "2026-09-30",
    });
  });

  it("shows the selected plan's coverage lane with no-gap feedback when fully priced", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    // Summer 2026's periods tile its effective range exactly (Jun 1 – Aug 31).
    expect(await screen.findByText("Coverage — Summer 2026")).toBeInTheDocument();
    expect(screen.getByText(/No gaps — every date in range has a rate period/)).toBeInTheDocument();
  });

  it("clicking a coverage gap opens the period dialog prefilled with the gap's inclusive range", async () => {
    setUser("reservations");
    installHandlers();
    // Shrink the plan to a single early period: Jun 21 – Aug 31 becomes a gap
    // (the plan is effective through Aug 31).
    server.use(
      http.get("/api/v1/rate-plans/100", () =>
        HttpResponse.json({ ...ratePlanDetail, periods: [ratePlanDetail.periods[0]] }),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    // ratePlanDetail.periods[0] runs Jun 1 – Jun 28. Writers get the
    // action-bearing accessible name.
    await user.click(
      await screen.findByRole("button", {
        name: "No rates, 29 Jun 2026 to 31 Aug 2026 — add a rate period",
      }),
    );
    await screen.findByRole("dialog");
    expectTriggerRange(/^dates/i, "29 Jun – 31 Aug 2026");
  });

  it("keeps coverage gaps inert for a non-writer", async () => {
    setUser("viewer");
    installHandlers();
    server.use(
      http.get("/api/v1/rate-plans/100", () =>
        HttpResponse.json({ ...ratePlanDetail, periods: [ratePlanDetail.periods[0]] }),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "No rates, 29 Jun 2026 to 31 Aug 2026" }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking a period's + opens the dialog prefilled with the day after that period", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    // "Peak" is the plan's last period (ends Aug 31) → its + starts Sep 1.
    await user.click(
      await screen.findByRole("button", { name: "Add a rate period starting 1 Sep 2026" }),
    );
    // "Standard" (Jun 1–28) is immediately followed by "Peak" (Jun 29–) — a
    // create there can never succeed, so it gets no + at all.
    expect(
      screen.queryByRole("button", { name: "Add a rate period starting 29 Jun 2026" }),
    ).toBeNull();
    await screen.findByRole("dialog");
    expectTriggerRange(/^dates/i, "1 Sep 2026 – …");
  });

  it("caps the + prefill at the day before the next period when there is a gap", async () => {
    setUser("reservations");
    installHandlers();
    // Pull "Peak" later so a Jun 29 – Jul 14 hole opens between the periods.
    server.use(
      http.get("/api/v1/rate-plans/100", () =>
        HttpResponse.json({
          ...ratePlanDetail,
          periods: [
            ratePlanDetail.periods[0],
            { ...ratePlanDetail.periods[1], date_from: "2026-07-15" },
          ],
        }),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Add a rate period starting 29 Jun 2026" }),
    );
    await screen.findByRole("dialog");
    expectTriggerRange(/^dates/i, "29 Jun – 14 Jul 2026");
  });

  it("scopes the timeline to the picker-selected plan when several plans exist", async () => {
    setUser("reservations");
    installHandlers();
    const winterPeriod = {
      id: 610,
      plan: 101,
      name: "Winter break",
      date_from: "2026-11-01",
      date_to: "2026-11-30",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 5, period: 610, min_party: 1, max_party: 8, nightly: "700" }],
    };
    server.use(
      http.get("/api/v1/properties/7/rate-plans", () =>
        HttpResponse.json(drfPage([season, winterSeason])),
      ),
      http.get("/api/v1/rate-plans/101", () =>
        HttpResponse.json({ ...winterSeason, periods: [winterPeriod] }),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    // Default selection is Summer (the first plan with periods): its bands show,
    // Winter's do not — the timeline reflects a single plan, not all of them.
    expect(await screen.findByRole("button", { name: /Standard, 1 Jun 2026/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Winter break, 1 Nov 2026/ })).toBeNull();

    // Switching the top picker re-scopes the whole timeline to the other plan.
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Choose a season" }));
    await user.click(await screen.findByRole("option", { name: /Winter 2026/ }));

    expect(
      await screen.findByRole("button", { name: /Winter break, 1 Nov 2026/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Standard, 1 Jun 2026/ })).toBeNull();
  });

  it("offers no per-period + to a non-writer", async () => {
    setUser("viewer");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    // Wait for the timeline (the period bands) to be on screen first.
    expect(await screen.findByRole("button", { name: /Standard, 1 Jun 2026/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rate period starting/ })).toBeNull();
  });

  it("offers no Add period affordance to a non-writer", async () => {
    setUser("viewer");
    installMultiSeasonHandlers();
    setup("/properties/casa-sur/rate-workbench");

    expect(await screen.findByRole("heading", { name: /Rate matrix/i })).toBeInTheDocument();
    // Role gating: the affordance disables, it never disappears.
    expect(await screen.findByRole("button", { name: "Add period" })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// GAP-060: the rate-plan (season) lifecycle affordances the old Pricing tab
// owned — create / edit / duplicate / delete — plus the GAP-026 currency
// mismatch warning, all brought into the workbench.
// ---------------------------------------------------------------------------

describe("RateWorkbenchPage — season lifecycle", () => {
  it("opens the create-season dialog from the header Add season button", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add season" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Add season" })).toBeInTheDocument();
  });

  it("bootstraps a plan-less property from the empty-state Add season CTA", async () => {
    setUser("reservations");
    server.use(
      http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    setup("/properties/casa-sur/rate-workbench");

    await screen.findByText(/No configuration yet/i);
    // Header button + empty-state CTA both offer season creation.
    const buttons = screen.getAllByRole("button", { name: "Add season" });
    expect(buttons).toHaveLength(2);
    const user = userEvent.setup();
    await user.click(buttons[1]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("opens the edit dialog for the active season from its actions menu", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Edit season" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Summer 2026");
  });

  it("duplicates the active season through a confirm dialog", async () => {
    setUser("reservations");
    installHandlers();
    let duplicated = false;
    server.use(
      http.post("/api/v1/rate-plans/100:duplicate", () => {
        duplicated = true;
        return HttpResponse.json(
          { ...season, id: 200, name: "Summer 2026 (copy)" },
          { status: 201 },
        );
      }),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Duplicate" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Duplicate" }));
    await waitFor(() => expect(duplicated).toBe(true));
  });

  it("deletes the active season through a destructive confirm dialog", async () => {
    setUser("reservations");
    installHandlers();
    let deleted = false;
    server.use(
      http.delete("/api/v1/rate-plans/100", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup("/properties/casa-sur/rate-workbench");

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("disables the Add season button for a non-writer", async () => {
    setUser("viewer");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    expect(await screen.findByRole("button", { name: "Add season" })).toBeDisabled();
  });

  it("warns when the active season's currency differs from the property currency", async () => {
    setUser("reservations");
    installHandlers();
    server.use(
      http.get("/api/v1/properties/7/settings", () =>
        HttpResponse.json({ property: 7, currency_code: "GBP" }),
      ),
    );
    setup("/properties/casa-sur/rate-workbench");

    expect(
      await screen.findByText(/prices in EUR, but the property's currency is GBP/i),
    ).toBeInTheDocument();
  });
});
