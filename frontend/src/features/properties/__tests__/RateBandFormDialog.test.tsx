import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { todayIso } from "@/lib/format/date";
import { useAuthStore } from "@/features/auth/store";
import { RateBandFormDialog } from "../components/RateBandFormDialog";
import type { RateBand } from "../schemas";

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

// GAP-056: a band is party × price only — dates live on the parent period.
const rule: RateBand = {
  id: 9,
  period: 5,
  min_party: 1,
  max_party: 8,
  nightly: "150.00",
  weekly: null,
  is_poa: false,
  is_locked: false,
  is_approved: true,
  notes: "",
};

function ruleResponse(body: Record<string, unknown>, id = 99) {
  return HttpResponse.json({ ...rule, ...body, id }, { status: 201 });
}

async function fillValidRule() {
  await userEvent.clear(screen.getByLabelText(/Maximum party/i));
  await userEvent.type(screen.getByLabelText(/Maximum party/i), "8");
  await userEvent.type(screen.getByLabelText(/Nightly price/i), "150.00");
}

describe("RateBandFormDialog — create", () => {
  it("posts to /periods/:id/bands normalising empty prices to null", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      min_party: 1,
      max_party: 8,
      nightly: "150.00",
      weekly: null,
      is_poa: false,
    });
    useAuthStore.getState().clear();
  });

  it("disables price inputs under POA and posts null prices despite typed values", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await userEvent.click(screen.getByLabelText(/price on application/i));
    expect(screen.getByLabelText(/Nightly price/i)).toBeDisabled();
    expect(screen.getByLabelText(/Weekly price/i)).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ is_poa: true, nightly: null, weekly: null });
    useAuthStore.getState().clear();
  });

  it("rejects max_party below min_party and fires no request", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/periods/5/bands", () => {
        requested = true;
        return ruleResponse({});
      }),
    );
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    // min_party defaults to 1; set it above max_party (which defaults to 1).
    await userEvent.clear(screen.getByLabelText(/Minimum party/i));
    await userEvent.type(screen.getByLabelText(/Minimum party/i), "9");
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/below minimum party/i)).toBeInTheDocument();
    expect(requested).toBe(false);
    useAuthStore.getState().clear();
  });

  it("requires a price or POA", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await userEvent.clear(screen.getByLabelText(/Nightly price/i));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/nightly or weekly price/i)).toBeInTheDocument();
    // Resolving the error by switching to POA clears it without another submit.
    await userEvent.click(screen.getByLabelText(/price on application/i));
    await waitFor(() =>
      expect(screen.queryByText(/nightly or weekly price/i)).not.toBeInTheDocument(),
    );
    useAuthStore.getState().clear();
  });

  it("Save & add another seeds the next band just above the saved max party", async () => {
    setReservationsUser();
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        return ruleResponse(body, 100 + bodies.length);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await userEvent.click(screen.getByRole("button", { name: /save & add another/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    // Next band seeds min_party/max_party = saved max_party + 1 (8 → 9), price cleared.
    const minParty = screen.getByLabelText(/Minimum party/i) as HTMLInputElement;
    await waitFor(() => expect(minParty.value).toBe("9"));
    expect((screen.getByLabelText(/Maximum party/i) as HTMLInputElement).value).toBe("9");
    expect((screen.getByLabelText(/Nightly price/i) as HTMLInputElement).value).toBe("");

    await userEvent.clear(screen.getByLabelText(/Maximum party/i));
    await userEvent.type(screen.getByLabelText(/Maximum party/i), "12");
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "175.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      min_party: 9,
      max_party: 12,
      nightly: "175.00",
    });
    useAuthStore.getState().clear();
  });
});

describe("RateBandFormDialog — flat (non-occupancy) plan", () => {
  afterEach(() => useAuthStore.getState().clear());

  it("hides the party inputs and posts a band spanning 1..capacity", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        pricesByOccupancy={false}
        capacity={12}
      />,
    );

    // No party inputs asked for on a flat plan.
    expect(screen.queryByLabelText(/Minimum party/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Maximum party/i)).not.toBeInTheDocument();
    // Nor the multi-band "save & add another" affordance.
    expect(screen.queryByRole("button", { name: /save & add another/i })).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Nightly price/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    // The single flat band must span the whole party range so any-size
    // bookings price (the engine matches party against the band even when flat).
    expect(postBody).toMatchObject({ min_party: 1, max_party: 12, nightly: "150.00" });
    useAuthStore.getState().clear();
  });

  it("falls back to max_party=1 when the property has no capacity row", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        pricesByOccupancy={false}
        capacity={null}
      />,
    );

    await userEvent.type(screen.getByLabelText(/Nightly price/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ min_party: 1, max_party: 1 });
    useAuthStore.getState().clear();
  });
});

describe("RateBandFormDialog — edit", () => {
  it("prefills from the rule and PATCHes edited fields", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/bands/9", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...rule, ...patchBody });
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="edit"
        rule={rule}
      />,
    );

    const nightlyInput = (await screen.findByLabelText(/Nightly price/i)) as HTMLInputElement;
    await waitFor(() => expect(nightlyInput.value).toBe("150.00"));
    await userEvent.clear(nightlyInput);
    await userEvent.type(nightlyInput, "275.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({ nightly: "275.00", weekly: null });
    useAuthStore.getState().clear();
  });
});

describe("RateBandFormDialog — currency adornment (GAP-026)", () => {
  afterEach(() => useAuthStore.getState().clear());

  it("shows the rate plan currency symbol beside both price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
      />,
    );
    // One adornment for nightly, one for weekly.
    expect(await screen.findAllByText("€")).toHaveLength(2);
  });

  it("renders no symbol when the season has no currency", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    expect(screen.queryByText("€")).not.toBeInTheDocument();
    expect(screen.queryByText("£")).not.toBeInTheDocument();
  });

  it("hides the symbol once POA masks the price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="GBP"
      />,
    );
    expect(await screen.findAllByText("£")).toHaveLength(2);
    await userEvent.click(screen.getByLabelText(/price on application/i));
    await waitFor(() => expect(screen.queryByText("£")).not.toBeInTheDocument());
  });
});

describe("RateBandFormDialog — reductions (Q-018)", () => {
  afterEach(() => useAuthStore.getState().clear());

  async function chooseKind(name: RegExp) {
    await userEvent.click(screen.getByRole("combobox", { name: /^reduction$/i }));
    await userEvent.click(screen.getByRole("option", { name }));
  }

  it("percent mode posts reduction_percent + metadata, nulling the fixed amounts", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await chooseKind(/^percentage$/i);
    await userEvent.type(screen.getByLabelText(/Reduction \(%\)/i), "10");
    await userEvent.type(screen.getByLabelText(/^Reason$/i), "Summer promo");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      reduction_percent: "10",
      reduced_nightly: null,
      reduced_weekly: null,
      reduction_reason: "Summer promo",
      // Enabling a reduction pre-fills "Reduced on" with today.
      reduced_at: todayIso(),
    });
    useAuthStore.getState().clear();
  });

  it("fixed mode offers one input per non-null base price and posts the reduced amount", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/periods/5/bands", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    // Nightly base only — the fixed mode must not ask for a reduced weekly.
    await userEvent.clear(screen.getByLabelText(/Maximum party/i));
    await userEvent.type(screen.getByLabelText(/Maximum party/i), "8");
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "200.00");
    await chooseKind(/fixed reduced prices/i);
    expect(screen.getByLabelText(/Reduced nightly price/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Reduced weekly price/i)).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Reduced nightly price/i), "150.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      nightly: "200.00",
      reduced_nightly: "150.00",
      reduced_weekly: null,
      reduction_percent: null,
    });
    useAuthStore.getState().clear();
  });

  it("6b: with both base prices, a fixed reduction needs both reduced amounts", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/periods/5/bands", () => {
        requested = true;
        return ruleResponse({});
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await userEvent.type(screen.getByLabelText(/Weekly price/i), "900.00");
    await chooseKind(/fixed reduced prices/i);
    await userEvent.type(screen.getByLabelText(/Reduced nightly price/i), "120.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/every base price/i)).toBeInTheDocument();
    expect(requested).toBe(false);
    useAuthStore.getState().clear();
  });

  it("shows the live effective price while entering a percent", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
      />,
    );
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "200.00");
    await chooseKind(/^percentage$/i);
    await userEvent.type(screen.getByLabelText(/Reduction \(%\)/i), "10");

    const hint = await screen.findByTestId("effective-price");
    expect(hint).toHaveTextContent(/Effective nightly/i);
    expect(hint).toHaveTextContent("€180.00");
  });

  it("switching back to no reduction sends nulls so the server clears everything", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/bands/9", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...rule, ...patchBody });
      }),
    );

    const reducedRule: RateBand = {
      ...rule,
      nightly: "200.00",
      reduction_percent: "10.00",
      reduced_at: "2026-07-01",
      reduction_reason: "Slow season",
      effective_nightly: "180.00",
    };
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="edit"
        rule={reducedRule}
      />,
    );
    // Edit mode prefills the stored reduction…
    const percentInput = (await screen.findByLabelText(/Reduction \(%\)/i)) as HTMLInputElement;
    expect(percentInput.value).toBe("10.00");
    // …and clearing it sends explicit nulls (reason clears to "" — the
    // backend field is a non-nullable CharField).
    await chooseKind(/no reduction/i);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({
      reduction_percent: null,
      reduced_nightly: null,
      reduced_weekly: null,
      reduced_at: null,
      reduction_reason: "",
    });
    useAuthStore.getState().clear();
  });

  it("clearing a base price clears its fixed reduced amount so the save isn't blocked", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/bands/9", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...rule, ...patchBody });
      }),
    );

    const fixedRule: RateBand = {
      ...rule,
      nightly: "200.00",
      weekly: "1200.00",
      reduced_nightly: "150.00",
      reduced_weekly: "900.00",
      reduced_at: "2026-07-01",
    };
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="edit"
        rule={fixedRule}
      />,
    );

    // RHF keeps unmounted values, so clearing the nightly base must take the
    // stale reduced_nightly with it — otherwise the hidden field's no-base
    // error silently blocks the save.
    const nightlyInput = (await screen.findByLabelText(/^Nightly price$/i)) as HTMLInputElement;
    await waitFor(() => expect(nightlyInput.value).toBe("200.00"));
    await userEvent.clear(nightlyInput);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({
      nightly: null,
      reduced_nightly: null,
      weekly: "1200.00",
      reduced_weekly: "900.00",
    });
    useAuthStore.getState().clear();
  });

  it("rejects a blank percent inline instead of silently dropping the typed metadata", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/periods/5/bands", () => {
        requested = true;
        return ruleResponse({});
      }),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    await fillValidRule();
    await chooseKind(/^percentage$/i);
    // Reason typed, percent left blank — must NOT save as "no reduction".
    await userEvent.type(screen.getByLabelText(/^Reason$/i), "Summer promo");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/enter the reduction/i)).toBeInTheDocument();
    expect(requested).toBe(false);
    useAuthStore.getState().clear();
  });

  it("surfaces server errors keyed to a reduction field whose input isn't mounted", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/periods/5/bands", () =>
        HttpResponse.json(
          {
            detail: "Validation failed",
            field_errors: {
              reduction_percent: ["The reduction must be between 0 and 100% (exclusive)."],
            },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
      />,
    );
    // Kind stays "none", so the percent input is unmounted — the 400 keyed on
    // reduction_percent must still show up somewhere visible.
    await fillValidRule();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/between 0 and 100/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});

describe("RateBandFormDialog — net↔gross derivation (GAP-035)", () => {
  afterEach(() => useAuthStore.getState().clear());

  const pct20 = { calculation_type: "percent", amount: "20.00" };
  const exemptTax = { percentage: "0", is_exempt: true };

  it("shows the derived owner net for a GROSS plan", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
        priceBasis="gross"
        commission={pct20}
        tax={exemptTax}
      />,
    );
    // gross 1000, 20% commission carved out → owner net 800
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "1000");
    const hint = await screen.findByTestId("derived-counterpart");
    expect(hint).toHaveTextContent(/Owner net/i);
    expect(hint).toHaveTextContent("€800.00");
  });

  it("shows the derived guest price for a NET plan (÷(1−pct), not ×(1+pct))", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
        priceBasis="net"
        commission={pct20}
        tax={exemptTax}
      />,
    );
    // net 800, 20% commission → guest price 1000 (800 / 0.8)
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "800");
    const hint = await screen.findByTestId("derived-counterpart");
    expect(hint).toHaveTextContent(/Guest price/i);
    expect(hint).toHaveTextContent("€1,000.00");
  });

  it("shows no hint when the basis is unknown", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
        commission={pct20}
      />,
    );
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "1000");
    expect(screen.queryByTestId("derived-counterpart")).not.toBeInTheDocument();
  });

  it("hides the hint once POA masks the price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        ratePlanId={11}
        periodId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        currencyCode="EUR"
        priceBasis="gross"
        commission={pct20}
        tax={exemptTax}
      />,
    );
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "1000");
    expect(await screen.findByTestId("derived-counterpart")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/price on application/i));
    await waitFor(() =>
      expect(screen.queryByTestId("derived-counterpart")).not.toBeInTheDocument(),
    );
  });
});
