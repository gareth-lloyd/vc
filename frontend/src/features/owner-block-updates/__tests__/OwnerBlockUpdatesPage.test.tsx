import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { OwnerBlockUpdatesPage } from "../OwnerBlockUpdatesPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function update(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    kind: "created",
    actor: 9,
    created_at: "2026-06-03T10:00:00Z",
    block: {
      id: 50,
      property: 3,
      property_name: "Villa Anemoi",
      date_from: "2026-08-01",
      date_to: "2026-08-08",
      kind: "owner_stay",
      notes: "",
      status: "approved",
      created_by: 9,
    },
    contested: null,
    is_seen: false,
    ...overrides,
  };
}

function grantWriterRole() {
  useAuthStore.setState({
    user: null,
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

beforeEach(() => {
  grantWriterRole();
});

afterEach(() => {
  server.resetHandlers();
});

describe("OwnerBlockUpdatesPage", () => {
  it("renders feed rows with property, kind and contested badges", async () => {
    server.use(
      http.get("/api/v1/owner-block-updates", () =>
        HttpResponse.json(
          drfPage([
            update(),
            update({
              id: 2,
              kind: "cancelled",
              is_seen: true,
              contested: { at: "2026-06-04T08:00:00Z", by: 12, reason: "Double booked" },
            }),
          ]),
        ),
      ),
    );

    renderWithProviders(<OwnerBlockUpdatesPage />, { route: "/owner-blocks" });

    expect(await screen.findAllByText("Villa Anemoi")).toHaveLength(2);
    expect(screen.getByText(/contested/i)).toBeInTheDocument();
  });

  it("drives seen=false when the unseen-only filter is toggled", async () => {
    const seenParams: Array<string | null> = [];
    server.use(
      http.get("/api/v1/owner-block-updates", ({ request }) => {
        seenParams.push(new URL(request.url).searchParams.get("seen"));
        return HttpResponse.json(drfPage([update()]));
      }),
    );

    renderWithProviders(<OwnerBlockUpdatesPage />, { route: "/owner-blocks" });

    await screen.findByText("Villa Anemoi");
    expect(seenParams[0]).toBeNull();

    await userEvent.click(screen.getByRole("checkbox", { name: /unseen only/i }));

    await waitFor(() => expect(seenParams).toContain("false"));
  });

  it("disables Contest on a cancelled block", async () => {
    server.use(
      http.get("/api/v1/owner-block-updates", () =>
        HttpResponse.json(
          drfPage([
            update({
              id: 2,
              kind: "cancelled",
              block: { ...update().block, status: "cancelled" },
            }),
          ]),
        ),
      ),
    );

    renderWithProviders(<OwnerBlockUpdatesPage />, { route: "/owner-blocks" });

    const row = (await screen.findByText("Villa Anemoi")).closest("li") as HTMLElement;
    expect(within(row).getByRole("button", { name: /contest/i })).toBeDisabled();
  });

  it("marks a row seen via the per-row action", async () => {
    let seenCalledFor: number | null = null;
    server.use(
      http.get("/api/v1/owner-block-updates", () => HttpResponse.json(drfPage([update()]))),
      http.post("/api/v1/owner-block-updates/1:seen", () => {
        seenCalledFor = 1;
        return HttpResponse.json(update({ is_seen: true }));
      }),
    );

    renderWithProviders(<OwnerBlockUpdatesPage />, { route: "/owner-blocks" });

    const row = (await screen.findByText("Villa Anemoi")).closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: /mark seen/i }));

    await waitFor(() => expect(seenCalledFor).toBe(1));
  });
});
