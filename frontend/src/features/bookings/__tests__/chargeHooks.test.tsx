import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { useCreateChargeItem, useDeleteChargeItem, useUpdateChargeItem } from "../hooks";
import type { BookingChargeItem } from "../schemas";

const BOOKING_ID = 51;

function makeItem(overrides: Partial<BookingChargeItem> = {}): BookingChargeItem {
  return {
    id: 1,
    booking: BOOKING_ID,
    label: "Late checkout",
    amount: "150.00",
    currency: 1,
    currency_code: "GBP",
    notes: "",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
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

// A charge mutation moves the booking total, the schedule and the timeline —
// every dependent cache must invalidate, not just the charge list.
const AFFECTED_KEYS = [
  queryKeys.bookings.chargeItems(BOOKING_ID),
  queryKeys.bookings.detail(BOOKING_ID),
  queryKeys.bookings.activity(BOOKING_ID),
  queryKeys.bookings.deposit(BOOKING_ID),
  queryKeys.bookings.balance(BOOKING_ID),
] as const;

function seedAffectedKeys(client: QueryClient): void {
  for (const key of AFFECTED_KEYS) {
    client.setQueryData(key, {});
  }
  client.setQueryData(queryKeys.bookings.list({}), {});
}

function expectAffectedKeysInvalidated(client: QueryClient): void {
  for (const key of AFFECTED_KEYS) {
    expect(client.getQueryState(key)?.isInvalidated, key.join("/")).toBe(true);
  }
  expect(client.getQueryState(queryKeys.bookings.list({}))?.isInvalidated).toBe(true);
}

describe("useCreateChargeItem", () => {
  it("POSTs the body and invalidates every total-dependent cache", async () => {
    const client = createClient();
    seedAffectedKeys(client);

    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/charge-items`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ id: 100 }), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useCreateChargeItem(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    let returned: BookingChargeItem | undefined;
    await act(async () => {
      returned = await result.current.mutateAsync({
        label: "Late checkout",
        amount: "150.00",
        notes: "",
      });
    });

    expect(returned?.id).toBe(100);
    expect(receivedBody).toMatchObject({ label: "Late checkout", amount: "150.00" });
    expectAffectedKeysInvalidated(client);
  });
});

describe("useUpdateChargeItem", () => {
  it("PATCHes the item and invalidates every total-dependent cache", async () => {
    const client = createClient();
    seedAffectedKeys(client);

    let receivedBody: unknown = null;
    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/charge-items/7`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeItem({ id: 7, amount: "-75.00" }));
      }),
    );

    const { result } = renderHook(() => useUpdateChargeItem(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ itemId: 7, input: { amount: "-75.00" } });
    });

    expect(receivedBody).toMatchObject({ amount: "-75.00" });
    expectAffectedKeysInvalidated(client);
  });
});

describe("useDeleteChargeItem", () => {
  it("DELETEs the item and invalidates every total-dependent cache", async () => {
    const client = createClient();
    seedAffectedKeys(client);

    server.use(
      http.delete(`/api/v1/bookings/${BOOKING_ID}/charge-items/7`, () =>
        HttpResponse.json(null, { status: 204 }),
      ),
    );

    const { result } = renderHook(() => useDeleteChargeItem(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ itemId: 7 });
    });

    expectAffectedKeysInvalidated(client);
  });
});
