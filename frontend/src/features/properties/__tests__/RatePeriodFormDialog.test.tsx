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
  bands: [],
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
  it("posts to /rate-plans/:id/rate-periods with the entered dates + name", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/rate-plans/11/rate-periods", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, plan: 11, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
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
      http.post("/api/v1/rate-plans/11/rate-periods", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, plan: 11, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
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
      http.post("/api/v1/rate-plans/11/rate-periods", () => {
        requested = true;
        return HttpResponse.json({ id: 1, plan: 11 }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
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
      http.post("/api/v1/rate-plans/11/rate-periods", () => {
        requested = true;
        return HttpResponse.json({ id: 1, plan: 11 }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
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
      http.post("/api/v1/rate-plans/11/rate-periods", () =>
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
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/Overlaps an existing rate period/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("renders an inline error for a 4xx field_errors.name (registered field, not folded)", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/rate-plans/11/rate-periods", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { name: ["A period with this name already exists."] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/A period with this name already exists/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts and stays open on a 5xx", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/rate-plans/11/rate-periods", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
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
        ratePlanId={11}
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

describe("RatePeriodFormDialog — changeover end-date suggestion (GAP-025 / SMELL-019)", () => {
  it("suggests date_to from a fixed changeover day once date_from is entered", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );

    // 2026-07-04 is a Saturday; sat changeover, 7-night min → Fri 10 Jul.
    await userEvent.type(screen.getByLabelText(/^From$/i), "2026-07-04");
    const dateTo = screen.getByLabelText(/^To$/i) as HTMLInputElement;
    await waitFor(() => expect(dateTo.value).toBe("2026-07-10"));
  });

  it("never clobbers a date_to the user has already typed", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );

    const dateTo = screen.getByLabelText(/^To$/i) as HTMLInputElement;
    await userEvent.type(dateTo, "2026-09-19");
    await userEvent.type(screen.getByLabelText(/^From$/i), "2026-07-04");

    // The manually typed value survives even though a suggestion would apply.
    expect(dateTo.value).toBe("2026-09-19");
  });

  it("makes no suggestion when the changeover day is 'any'", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        changeoverDay="any"
        minNightsRental={7}
      />,
    );

    await userEvent.type(screen.getByLabelText(/^From$/i), "2026-07-04");
    const dateTo = screen.getByLabelText(/^To$/i) as HTMLInputElement;
    await new Promise((r) => setTimeout(r, 0));
    expect(dateTo.value).toBe("");
  });

  it("leaves the stored date_to untouched in edit mode", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="edit"
        period={period}
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );

    const dateTo = screen.getByLabelText(/^To$/i) as HTMLInputElement;
    await new Promise((r) => setTimeout(r, 0));
    expect(dateTo.value).toBe("2026-06-30");
  });
});

describe("RatePeriodFormDialog — create with initialValues (workbench prefill)", () => {
  it("prefills date_from and lets the changeover suggestion complete date_to", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        initialValues={{ date_from: "2026-09-01" }}
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );
    expect(screen.getByLabelText(/^From$/i)).toHaveValue("2026-09-01");
    // GAP-025 suggestion still fires off the prefilled start date.
    await waitFor(() => expect(screen.getByLabelText(/^To$/i)).not.toHaveValue(""));
  });

  it("never clobbers an initialValues date_to with the changeover suggestion", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        initialValues={{ date_from: "2026-09-01", date_to: "2026-09-30" }}
        changeoverDay="sat"
        minNightsRental={7}
      />,
    );
    expect(screen.getByLabelText(/^From$/i)).toHaveValue("2026-09-01");
    // A caller-provided end date wins over the weekday suggestion, always.
    await waitFor(() => expect(screen.getByLabelText(/^To$/i)).toHaveValue("2026-09-30"));
  });
});

describe("RatePeriodFormDialog — compulsory name + date-span suggestion (GAP-059)", () => {
  it("suggests the date-span name once both dates are entered", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await waitFor(() => expect(screen.getByLabelText(/^Name$/i)).toHaveValue("1–30 Jun"));
  });

  it("blocks save when the name is cleared and fires no request", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/rate-plans/11/rate-periods", () => {
        requested = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await fillValidPeriod();
    await userEvent.clear(screen.getByLabelText(/^Name$/i));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(requested).toBe(false);
  });

  it("never clobbers a name the user typed", async () => {
    setReservationsUser();
    renderWithProviders(
      <RatePeriodFormDialog ratePlanId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(screen.getByLabelText(/^Name$/i), "Peak summer");
    await fillValidPeriod();
    expect(screen.getByLabelText(/^Name$/i)).toHaveValue("Peak summer");
  });

  it("prefills the name from a coverage-gap prefill so one keystroke saves", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/rate-plans/11/rate-periods", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, plan: 11, ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <RatePeriodFormDialog
        ratePlanId={11}
        open
        onOpenChange={() => {}}
        mode="create"
        initialValues={{ date_from: "2026-09-01", date_to: "2026-09-30" }}
      />,
    );
    await waitFor(() => expect(screen.getByLabelText(/^Name$/i)).toHaveValue("1–30 Sep"));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({
      name: "1–30 Sep",
      date_from: "2026-09-01",
      date_to: "2026-09-30",
    });
  });
});
