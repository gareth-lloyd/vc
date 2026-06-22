import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { useOwnerStore } from "../ownerStore";
import { useOwnerBookings, useOwnerDashboard, useOwnerMe } from "../hooks";

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  useOwnerStore.setState({ status: "idle", organisations: [] });
});

describe("useOwnerMe", () => {
  it("records owner status + organisations when /owner/me succeeds", async () => {
    server.use(
      http.get("/api/v1/owner/me", () =>
        HttpResponse.json({
          user: {
            id: 1,
            email: "owner@example.com",
            first_name: "Kostas",
            last_name: "Papas",
            is_active: true,
            is_staff: false,
            is_superuser: false,
          },
          is_owner: true,
          organisations: [
            {
              id: 9,
              name: "Kostas Hospitality Ltd",
              role: "owner",
              properties: [{ property_id: 3, view_full_money: true, view_guest_details: false }],
            },
          ],
        }),
      ),
    );
    const client = createClient();
    renderHook(() => useOwnerMe(true), { wrapper: wrapper(client) });
    await waitFor(() => expect(useOwnerStore.getState().status).toBe("owner"));
    expect(useOwnerStore.getState().organisations[0].name).toBe("Kostas Hospitality Ltd");
  });

  it("records not_owner on a 200 {is_owner:false} body without throwing", async () => {
    server.use(
      http.get("/api/v1/owner/me", () =>
        HttpResponse.json({
          user: {
            id: 1,
            email: "owner@example.com",
            first_name: "Kostas",
            last_name: "Papas",
            is_active: true,
            is_staff: false,
            is_superuser: false,
          },
          is_owner: false,
          organisations: [],
        }),
      ),
    );
    const client = createClient();
    const { result } = renderHook(() => useOwnerMe(true), { wrapper: wrapper(client) });
    await waitFor(() => expect(useOwnerStore.getState().status).toBe("not_owner"));
    expect(result.current.isError).toBe(false);
  });

  it("records a retryable error (not not_owner) on a 5xx so the guards never hang", async () => {
    server.use(
      http.get("/api/v1/owner/me", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    const client = createClient();
    const { result } = renderHook(() => useOwnerMe(true), { wrapper: wrapper(client) });
    // Store leaves "idle" (otherwise RequireStaff/RequireOwner wait forever) but
    // lands on "error", NOT "not_owner": a 5xx is indeterminate and must stay
    // retryable rather than locking a genuine owner out for staleTime.
    await waitFor(() => expect(useOwnerStore.getState().status).toBe("error"));
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useOwnerBookings", () => {
  it("fetches and parses a redacted booking row (money absent)", async () => {
    server.use(
      http.get("/api/v1/owner/bookings", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 7,
              reference: "VC-0007",
              status: "deposit_paid",
              property_id: 3,
              property_name: "Villa Anemoi",
              date_from: "2026-07-01",
              date_to: "2026-07-08",
              adults: 2,
              children: 0,
              currency_code: "EUR",
              guest_name: "Ada Lovelace",
              guest_country: { code: "GB", name: "United Kingdom" },
              is_repeat_guest: false,
              can_approve: false,
            },
          ]),
        ),
      ),
    );
    const client = createClient();
    const { result } = renderHook(() => useOwnerBookings({ page: 1 }), {
      wrapper: wrapper(client),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.results[0].reference).toBe("VC-0007");
    expect(result.current.data?.results[0].rental_price).toBeUndefined();
  });
});

describe("useOwnerDashboard", () => {
  it("fetches the dashboard payload", async () => {
    server.use(
      http.get("/api/v1/owner/dashboard", () =>
        HttpResponse.json({
          ytd: { bookings: 5, gross_revenue: null, net_to_owner: null },
          properties: { total: 2, by_status: { active: 2 } },
          upcoming_arrivals: [],
        }),
      ),
    );
    const client = createClient();
    const { result } = renderHook(() => useOwnerDashboard(), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.ytd.bookings).toBe(5);
  });
});
