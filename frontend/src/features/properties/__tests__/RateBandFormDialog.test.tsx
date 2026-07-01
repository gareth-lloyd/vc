import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
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
        seasonId={11}
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
        seasonId={11}
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
      <RateBandFormDialog seasonId={11} periodId={5} open onOpenChange={() => {}} mode="create" />,
    );
    expect(screen.queryByText("€")).not.toBeInTheDocument();
    expect(screen.queryByText("£")).not.toBeInTheDocument();
  });

  it("hides the symbol once POA masks the price inputs", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        seasonId={11}
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

describe("RateBandFormDialog — net↔gross derivation (GAP-035)", () => {
  afterEach(() => useAuthStore.getState().clear());

  const pct20 = { calculation_type: "percent", amount: "20.00" };
  const exemptTax = { percentage: "0", is_exempt: true };

  it("shows the derived owner net for a GROSS plan", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateBandFormDialog
        seasonId={11}
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
        seasonId={11}
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
        seasonId={11}
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
        seasonId={11}
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
