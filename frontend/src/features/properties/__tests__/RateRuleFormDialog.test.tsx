import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
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
  priority: 0,
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
    await waitFor(() => expect(fromInput.value).toBe("2026-06-08"));
    expect((screen.getByLabelText(/Maximum party/i) as HTMLInputElement).value).toBe("8");
    expect((screen.getByLabelText(/Nightly price/i) as HTMLInputElement).value).toBe("");

    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-15");
    await userEvent.type(screen.getByLabelText(/Nightly price/i), "175.00");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      date_from: "2026-06-08",
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
