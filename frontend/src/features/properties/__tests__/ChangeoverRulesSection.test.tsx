import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { ChangeoverRulesSection } from "../components/ChangeoverRulesSection";

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

const ruleFixture = {
  id: 50,
  property: 7,
  weekday: "sat",
  effective_from: "2026-06-01",
  effective_to: "2026-09-30",
  notes: "Peak season",
};

describe("ChangeoverRulesSection", () => {
  it("renders rules with weekday label and date range", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/change-over-rules", () =>
        HttpResponse.json(drfPage([ruleFixture])),
      ),
    );
    renderWithProviders(<ChangeoverRulesSection propertyId={7} />);
    expect(await screen.findByText("Saturday")).toBeInTheDocument();
    expect(screen.getByText(/2026-06-01.*2026-09-30/)).toBeInTheDocument();
    expect(screen.getByText("Peak season")).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("creates a new rule via POST to /properties/{id}/change-over-rules", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/change-over-rules", async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...ruleFixture, ...posted }, { status: 201 });
      }),
    );

    renderWithProviders(<ChangeoverRulesSection propertyId={7} />);
    await userEvent.click(await screen.findByRole("button", { name: /add rule/i }));
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(userEvent, picker, { from: "2026-06-01", to: "2026-09-30" });
    expectTriggerRange(/^dates/i, "1 Jun – 30 Sep 2026 · 122 days");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.effective_from).toBe("2026-06-01");
    expect(posted!.effective_to).toBe("2026-09-30");
    expect(posted!.weekday).toBe("sat");
    useAuthStore.getState().clear();
  });

  it("deletes the rule via DELETE to /change-over-rules/{id} (non-nested)", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/change-over-rules", () =>
        HttpResponse.json(drfPage([ruleFixture])),
      ),
    );
    let deleted = false;
    server.use(
      http.delete("/api/v1/change-over-rules/50", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(<ChangeoverRulesSection propertyId={7} />);
    await waitFor(() => expect(screen.getByText("Saturday")).toBeInTheDocument());
    const menu = await screen.findByRole("button", { name: /actions/i });
    await userEvent.click(menu);
    await userEvent.click(await screen.findByText(/^Delete$/i));
    await userEvent.click(await screen.findByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(deleted).toBe(true));
    useAuthStore.getState().clear();
  });
});
