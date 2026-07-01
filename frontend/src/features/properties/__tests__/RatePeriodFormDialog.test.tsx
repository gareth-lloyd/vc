import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { RatePeriodFormDialog } from "../components/RatePeriodFormDialog";
import type { RatePeriod } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

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

const period: RatePeriod = {
  id: 7,
  plan: 11,
  name: "Peak summer",
  date_from: "2026-06-01",
  date_to: "2026-06-30",
  min_nights: 7,
  max_nights: 30,
  is_active: true,
  rules: [],
  coverage_gaps: [],
};

afterEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  useAuthStore.getState().clear();
});

async function fillValidPeriod() {
  await userEvent.type(screen.getByLabelText(/^From$/i), "2026-06-01");
  await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-30");
}

describe("RatePeriodFormDialog — create", () => {
  it("posts to /seasons/:id/rate-periods with the entered dates + name", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, plan: 11, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(screen.getByLabelText(/Name/i), "Peak summer");
    await fillValidPeriod();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      name: "Peak summer",
      date_from: "2026-06-01",
      date_to: "2026-06-30",
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it("posts nullable min/max-nights overrides when supplied", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, plan: 11, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.type(screen.getByLabelText(/Minimum nights/i), "7");
    await userEvent.type(screen.getByLabelText(/Maximum nights/i), "30");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ min_nights: 7, max_nights: 30 });
  });

  it("rejects date_to before date_from and fires no request (dates re-homed from the rule)", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", () => {
        requested = true;
        return HttpResponse.json({ id: 1, plan: 11 }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(screen.getByLabelText(/^From$/i), "2026-06-30");
    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-01");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/on or after From date/i)).toBeInTheDocument();
    expect(requested).toBe(false);
  });

  it("rejects max_nights below min_nights and fires no request", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", () => {
        requested = true;
        return HttpResponse.json({ id: 1, plan: 11 }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.type(screen.getByLabelText(/Minimum nights/i), "7");
    await userEvent.type(screen.getByLabelText(/Maximum nights/i), "3");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/below minimum nights/i)).toBeInTheDocument();
    expect(requested).toBe(false);
  });

  it("maps a 4xx field error to an inline message", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { date_to: ["Overlaps an existing rate period."] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/Overlaps an existing rate period/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts and stays open on a 5xx", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/seasons/11/rate-periods", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(
      <RatePeriodFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // Dialog stays open — the form is still on screen.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
  });
});

describe("RatePeriodFormDialog — edit", () => {
  it("prefills from the period and PATCHes /periods/:id", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/periods/7", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...period, ...patchBody });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog
        seasonId={11}
        open
        onOpenChange={() => {}}
        mode="edit"
        period={period}
      />,
    );

    const nameInput = (await screen.findByLabelText(/Name/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Peak summer"));
    expect((screen.getByLabelText(/^From$/i) as HTMLInputElement).value).toBe("2026-06-01");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Renamed peak");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({ name: "Renamed peak" });
    expect(toast.success).toHaveBeenCalled();
  });
});
