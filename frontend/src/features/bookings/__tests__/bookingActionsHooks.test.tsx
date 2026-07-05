import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import {
  useArchiveBooking,
  useCancelBooking,
  useCheckInBooking,
  useCheckOutBooking,
  useConfirmBooking,
  useDeclineBooking,
  useModifyBookingDates,
  useModifyBookingGuests,
  useResendBookingConfirmation,
  useRestoreBooking,
} from "../hooks";
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

async function assertActionHook<TVars>(opts: {
  result: { current: { mutateAsync: (v: TVars) => Promise<unknown> } };
  client: QueryClient;
  path: string;
  args: TVars;
  expectedBody: unknown;
  responseStatus: BookingDetail["status"];
  detailKey: ReturnType<typeof queryKeys.bookings.detail>;
  listKey: ReturnType<typeof queryKeys.bookings.list>;
  pathTracker: { value: string | null };
  bodyTracker: { value: unknown };
}) {
  await act(async () => {
    await opts.result.current.mutateAsync(opts.args);
  });

  expect(opts.pathTracker.value).toBe(`/api/v1/bookings/${BOOKING_ID}${opts.path}`);
  expect(opts.bodyTracker.value).toEqual(opts.expectedBody);
  expect(opts.client.getQueryData<BookingDetail>(opts.detailKey)?.status).toBe(opts.responseStatus);
  expect(opts.client.getQueryState(opts.listKey)?.isInvalidated).toBe(true);
  expect(opts.client.getQueryState(opts.detailKey)?.isInvalidated).toBe(false);
}

function setupActionFixture(verbPath: string, responseStatus: BookingDetail["status"]) {
  const client = createClient();
  const detailKey = queryKeys.bookings.detail(BOOKING_ID);
  const listKey = queryKeys.bookings.list({ q: "x" });
  client.setQueryData(detailKey, makeBookingDetail());
  client.setQueryData(listKey, { count: 0, next: null, previous: null, results: [] });

  const pathTracker = { value: null as string | null };
  const bodyTracker = { value: "unread" as unknown };
  server.use(
    http.post(`/api/v1/bookings/${BOOKING_ID}${verbPath}`, async ({ request }) => {
      pathTracker.value = new URL(request.url).pathname;
      const text = await request.text();
      bodyTracker.value = text === "" ? null : JSON.parse(text);
      return HttpResponse.json(makeBookingDetail({ status: responseStatus }));
    }),
  );

  return { client, detailKey, listKey, pathTracker, bodyTracker };
}

describe("booking action hooks — happy paths", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("useDeclineBooking POSTs :owner-decline with reason", async () => {
    const fx = setupActionFixture(":owner-decline", "declined");
    const { result } = renderHook(() => useDeclineBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":owner-decline",
      args: { reason: "owner declined" },
      expectedBody: { reason: "owner declined" },
      responseStatus: "declined",
    });
  });

  it("useModifyBookingDates POSTs :modify-dates with date_from/date_to/reason", async () => {
    const fx = setupActionFixture(":modify-dates", "deposit_paid");
    const { result } = renderHook(() => useModifyBookingDates(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":modify-dates",
      args: { date_from: "2026-07-10", date_to: "2026-07-17", reason: "guest req" },
      expectedBody: { date_from: "2026-07-10", date_to: "2026-07-17", reason: "guest req" },
      responseStatus: "deposit_paid",
    });
  });

  it("useModifyBookingGuests POSTs :modify-guests with adults/children", async () => {
    const fx = setupActionFixture(":modify-guests", "deposit_paid");
    const { result } = renderHook(() => useModifyBookingGuests(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":modify-guests",
      args: { adults: 3, children: 1 },
      expectedBody: { adults: 3, children: 1 },
      responseStatus: "deposit_paid",
    });
  });

  it("useArchiveBooking POSTs :archive with no body", async () => {
    const fx = setupActionFixture(":archive", "checked_out");
    const { result } = renderHook(() => useArchiveBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":archive",
      args: undefined,
      expectedBody: null,
      responseStatus: "checked_out",
    });
  });

  it("useRestoreBooking POSTs :restore with no body", async () => {
    const fx = setupActionFixture(":restore", "checked_out");
    const { result } = renderHook(() => useRestoreBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":restore",
      args: undefined,
      expectedBody: null,
      responseStatus: "checked_out",
    });
  });

  it("useCheckInBooking POSTs :check-in with no body", async () => {
    const fx = setupActionFixture(":check-in", "checked_in");
    const { result } = renderHook(() => useCheckInBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":check-in",
      args: undefined,
      expectedBody: null,
      responseStatus: "checked_in",
    });
  });

  it("useCheckOutBooking POSTs :check-out with no body", async () => {
    const fx = setupActionFixture(":check-out", "checked_out");
    const { result } = renderHook(() => useCheckOutBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":check-out",
      args: undefined,
      expectedBody: null,
      responseStatus: "checked_out",
    });
  });

  it("useResendBookingConfirmation POSTs :resend-confirmation with no body", async () => {
    const fx = setupActionFixture(":resend-confirmation", "awaiting_deposit");
    const { result } = renderHook(() => useResendBookingConfirmation(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });
    await assertActionHook({
      result,
      ...fx,
      path: ":resend-confirmation",
      args: undefined,
      expectedBody: null,
      responseStatus: "awaiting_deposit",
    });
  });
});

describe("BUG-018 — lifecycle mutations refresh availability + contact sub-tabs", () => {
  // The response payload carries `property: 12` (makeBookingDetail), which
  // must fan out to that property's availability caches, the cross-property
  // timeline, and (broadly — no contact FK on bookings) contact sub-tabs.
  function seedCrossEntityKeys(client: QueryClient) {
    const keys = [
      queryKeys.properties.availabilityCalendar(12, "2026-07-01", "2026-07-31"),
      queryKeys.properties.holds(12, "2026-07-01", "2026-07-31"),
      queryKeys.properties.bookingsInRange(12, "2026-07-01", "2026-07-31"),
      queryKeys.availability.timeline([12], "2026-07-01", "2026-07-31"),
      queryKeys.contacts.bookings(7),
      queryKeys.bookings.statusCountsAll(),
    ];
    for (const key of keys) {
      client.setQueryData(key, {});
    }
    return keys;
  }

  function expectAllInvalidated(client: QueryClient, keys: readonly (readonly unknown[])[]) {
    for (const key of keys) {
      expect(client.getQueryState(key)?.isInvalidated, key.join("/")).toBe(true);
    }
  }

  it("useModifyBookingDates invalidates the property's availability caches and contact sub-tabs", async () => {
    const fx = setupActionFixture(":modify-dates", "deposit_paid");
    const keys = seedCrossEntityKeys(fx.client);
    const { result } = renderHook(() => useModifyBookingDates(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });

    await act(async () => {
      await result.current.mutateAsync({
        date_from: "2026-07-10",
        date_to: "2026-07-17",
        reason: "guest req",
      });
    });

    expectAllInvalidated(fx.client, keys);
  });

  it("useConfirmBooking invalidates the property's availability caches and contact sub-tabs", async () => {
    const fx = setupActionFixture(":confirm", "awaiting_deposit");
    const keys = seedCrossEntityKeys(fx.client);
    const { result } = renderHook(() => useConfirmBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expectAllInvalidated(fx.client, keys);
  });

  it("useCancelBooking invalidates the property's availability caches and contact sub-tabs", async () => {
    const fx = setupActionFixture(":cancel", "cancelled");
    const keys = seedCrossEntityKeys(fx.client);
    const { result } = renderHook(() => useCancelBooking(BOOKING_ID), {
      wrapper: wrapperWith(fx.client),
    });

    await act(async () => {
      await result.current.mutateAsync({ reason: "guest no-show" });
    });

    expectAllInvalidated(fx.client, keys);
  });
});

describe("useDeclineBooking error envelope", () => {
  it("rejects with an ApiError on 400 so callers can apply field errors", async () => {
    const client = createClient();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:owner-decline`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { reason: ["Required"] },
          },
          { status: 400 },
        ),
      ),
    );

    const { result } = renderHook(() => useDeclineBooking(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    let error: unknown = null;
    await act(async () => {
      try {
        await result.current.mutateAsync({ reason: "" });
      } catch (e) {
        error = e;
      }
    });

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).fieldErrors).toEqual({ reason: ["Required"] });
  });
});
