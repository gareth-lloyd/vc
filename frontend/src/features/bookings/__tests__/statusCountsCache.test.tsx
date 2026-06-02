import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { useBookingStatusCounts, useConfirmBooking } from "../hooks";
import type { BookingDetail, BookingFilters } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
}

function wrapperWith(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

describe("useBookingStatusCounts cache key", () => {
  it("does not refetch when only status / page / ordering differ", async () => {
    let hits = 0;
    server.use(
      http.get("/api/v1/bookings/status-counts", () => {
        hits += 1;
        return HttpResponse.json({ draft: 1, deposit_paid: 2 });
      }),
    );
    const client = createClient();

    // First filter state — fetches once.
    const first = renderHook(
      ({ filters }: { filters: BookingFilters }) => useBookingStatusCounts(filters),
      { wrapper: wrapperWith(client), initialProps: { filters: { status: "draft", page: 2 } } },
    );
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    expect(hits).toBe(1);

    // Differs only in the stripped fields (status/page/ordering) → same key, no refetch.
    const second = renderHook(
      ({ filters }: { filters: BookingFilters }) => useBookingStatusCounts(filters),
      {
        wrapper: wrapperWith(client),
        initialProps: { filters: { status: "deposit_paid", page: 5, ordering: "-created_at" } },
      },
    );
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));
    expect(hits).toBe(1);
  });
});

function makeBookingDetail(overrides: Partial<BookingDetail> = {}): BookingDetail {
  return {
    id: 51,
    reference: "B-AAA-001",
    status: "awaiting_deposit",
    property: 12,
    guest: 99,
    agent: null,
    assigned_to: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 4,
    children: 2,
    currency: 1,
    rental_price: "1500.00",
    balance_due: "1000.00",
    balance_due_at: "2026-06-01",
    site_source: "main_website",
    is_archived: false,
    archived_at: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-02T00:00:00Z",
    ...overrides,
  };
}

describe("booking status transition", () => {
  it("invalidates the status-counts badge cache on confirm", async () => {
    const client = createClient();
    // Seed a cached counts query under the status-counts prefix.
    const countsKey = queryKeys.bookings.statusCounts({});
    client.setQueryData(countsKey, { draft: 3 });

    server.use(
      http.post("/api/v1/bookings/51:confirm", () =>
        HttpResponse.json(makeBookingDetail({ status: "awaiting_deposit" })),
      ),
    );

    const { result } = renderHook(() => useConfirmBooking(51), { wrapper: wrapperWith(client) });
    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(client.getQueryState(countsKey)?.isInvalidated).toBe(true);
  });
});
