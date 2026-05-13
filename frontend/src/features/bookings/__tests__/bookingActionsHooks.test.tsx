import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import { useCancelBooking, useConfirmBooking } from "../hooks";
import type { BookingDetail } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const BOOKING_ID = 51;

function makeBookingDetail(overrides: Partial<BookingDetail> = {}): BookingDetail {
  return {
    id: BOOKING_ID,
    reference: "B-AAA-001",
    status: "draft",
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

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
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
});

describe("useConfirmBooking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs to :confirm with no body, writes response into detail cache, invalidates activity + lists but not detail", async () => {
    const client = createClient();
    const detailKey = queryKeys.bookings.detail(BOOKING_ID);
    const activityKey = queryKeys.bookings.activity(BOOKING_ID);
    const listKey = queryKeys.bookings.list({ q: "x" });
    client.setQueryData(detailKey, makeBookingDetail({ status: "draft" }));
    client.setQueryData(activityKey, { count: 0, next: null, previous: null, results: [] });
    client.setQueryData(listKey, { count: 0, next: null, previous: null, results: [] });

    let receivedBody: unknown = "unread";
    let receivedPath: string | null = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:confirm`, async ({ request }) => {
        receivedPath = new URL(request.url).pathname;
        const text = await request.text();
        receivedBody = text === "" ? null : JSON.parse(text);
        return HttpResponse.json(makeBookingDetail({ status: "awaiting_deposit" }));
      }),
    );

    const { result } = renderHook(() => useConfirmBooking(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(receivedPath).toBe(`/api/v1/bookings/${BOOKING_ID}:confirm`);
    expect(receivedBody).toBeNull();
    expect(client.getQueryData<BookingDetail>(detailKey)?.status).toBe("awaiting_deposit");
    expect(client.getQueryState(activityKey)?.isInvalidated).toBe(true);
    expect(client.getQueryState(listKey)?.isInvalidated).toBe(true);
    expect(client.getQueryState(detailKey)?.isInvalidated).toBe(false);
  });
});

describe("useCancelBooking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs to :cancel with the reason body and updates the detail cache", async () => {
    const client = createClient();
    const detailKey = queryKeys.bookings.detail(BOOKING_ID);
    client.setQueryData(detailKey, makeBookingDetail({ status: "deposit_paid" }));

    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(
          makeBookingDetail({
            status: "cancelled",
            cancel_reason: "guest no-show",
            cancelled_at: "2026-05-13T10:00:00Z",
          }),
        );
      }),
    );

    const { result } = renderHook(() => useCancelBooking(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ reason: "guest no-show" });
    });

    expect(receivedBody).toEqual({ reason: "guest no-show" });
    expect(client.getQueryData<BookingDetail>(detailKey)?.status).toBe("cancelled");
  });

  it("rejects with an ApiError on 400 so callers can apply field errors", async () => {
    const client = createClient();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { reason: ["Too long"] },
          },
          { status: 400 },
        ),
      ),
    );

    const { result } = renderHook(() => useCancelBooking(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    let error: unknown = null;
    await act(async () => {
      try {
        await result.current.mutateAsync({ reason: "x" });
      } catch (e) {
        error = e;
      }
    });

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).fieldErrors).toEqual({ reason: ["Too long"] });
  });
});
