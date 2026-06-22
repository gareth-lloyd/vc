import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { RateRuleFormDialog } from "../components/RateRuleFormDialog";
import type { RateRule } from "../schemas";

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

const rule: RateRule = {
  id: 9,
  card: 5,
  date_from: "2026-06-01",
  date_to: "2026-06-08",
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
  await userEvent.type(await screen.findByLabelText(/^From$/i), "2026-06-01");
  await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-08");
  await userEvent.clear(screen.getByLabelText(/Maximum party/i));
  await userEvent.type(screen.getByLabelText(/Maximum party/i), "8");
  await userEvent.type(screen.getByLabelText(/Nightly price/i), "150.00");
}

describe("RateRuleFormDialog — create", () => {
  it("posts to /rate-cards/:id/rules normalising empty prices to null", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/rate-cards/5/rules", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidRule();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      date_from: "2026-06-01",
      date_to: "2026-06-08",
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
      http.post("/api/v1/rate-cards/5/rules", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return ruleResponse(postBody);
      }),
    );

    renderWithProviders(
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
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

  it("rejects date_to equal to date_from and fires no request", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/rate-cards/5/rules", () => {
        requested = true;
        return ruleResponse({});
      }),
    );
    renderWithProviders(
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidRule();
    const toInput = screen.getByLabelText(/^To$/i);
    await userEvent.clear(toInput);
    await userEvent.type(toInput, "2026-06-01");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/must be after the start date/i)).toBeInTheDocument();
    expect(requested).toBe(false);
    useAuthStore.getState().clear();
  });

  it("requires a price or POA", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
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

  it("Save & add another keeps the dialog open seeded from the saved rule", async () => {
    setReservationsUser();
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/v1/rate-cards/5/rules", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        return ruleResponse(body, 100 + bodies.length);
      }),
    );

    renderWithProviders(
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidRule();
    await userEvent.click(screen.getByRole("button", { name: /save & add another/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    const fromInput = screen.getByLabelText(/^From$/i) as HTMLInputElement;
    await waitFor(() => expect(fromInput.value).toBe("2026-06-09"));
    expect((screen.getByLabelText(/Maximum party/i) as HTMLInputElement).value).toBe("8");
    expect((screen.getByLabelText(/Nightly price/i) as HTMLInputElement).value).toBe("");

    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-15");
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "175.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      date_from: "2026-06-09",
      date_to: "2026-06-15",
      nightly: "175.00",
    });
    useAuthStore.getState().clear();
  });
});

describe("RateRuleFormDialog — edit", () => {
  it("prefills from the rule and PATCHes edited fields", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/rules/9", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...rule, ...patchBody });
      }),
    );

    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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

describe("RateRuleFormDialog — changeover end-date suggestion (GAP-025)", () => {
  afterEach(() => useAuthStore.getState().clear());

  it("suggests date_to from a fixed changeover day once date_from is seeded", async () => {
    setReservationsUser();
    // 2026-07-04 is a Saturday; sat changeover, 7-night min → Fri 10 Jul.
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        defaults={{ date_from: "2026-07-04" }}
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );

    const dateTo = (await screen.findByLabelText(/^To$/i)) as HTMLInputElement;
    await waitFor(() => expect(dateTo.value).toBe("2026-07-10"));
  });

  it("never clobbers a date_to the user has already typed", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );

    const dateTo = (await screen.findByLabelText(/^To$/i)) as HTMLInputElement;
    await userEvent.type(dateTo, "2026-09-19");
    await userEvent.type(screen.getByLabelText(/^From$/i), "2026-07-04");

    // Manual value survives even though a suggestion would otherwise apply.
    expect(dateTo.value).toBe("2026-09-19");
  });

  it("makes no suggestion when the changeover day is 'any'", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        defaults={{ date_from: "2026-07-04" }}
        changeoverDay="any"
        minNightsRental={7}
      />,
    );

    const dateTo = (await screen.findByLabelText(/^To$/i)) as HTMLInputElement;
    // Give the effect a chance to (not) run.
    await new Promise((r) => setTimeout(r, 0));
    expect(dateTo.value).toBe("");
  });
});

describe("RateRuleFormDialog — currency adornment (GAP-026)", () => {
  afterEach(() => useAuthStore.getState().clear());

  it("shows the rate plan currency symbol beside both price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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
      <RateRuleFormDialog seasonId={11} cardId={5} open onOpenChange={() => {}} mode="create" />,
    );
    expect(screen.queryByText("€")).not.toBeInTheDocument();
    expect(screen.queryByText("£")).not.toBeInTheDocument();
  });

  it("hides the symbol once POA masks the price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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

describe("RateRuleFormDialog — net↔gross derivation (GAP-035)", () => {
  afterEach(() => useAuthStore.getState().clear());

  const pct20 = { calculation_type: "percent", amount: "20.00" };
  const exemptTax = { percentage: "0", is_exempt: true };

  it("shows the derived owner net for a GROSS plan", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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
      <RateRuleFormDialog
        seasonId={11}
        cardId={5}
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
