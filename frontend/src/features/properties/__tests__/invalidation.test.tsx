import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/render";
import { server } from "@/test/msw/server";
import { invalidatedKeys } from "@/test/invalidation";
import { queryKeys } from "@/lib/query/keys";
import { useArchiveProperty, useCreatePropertyBlock, useUpdatePropertyFeatures } from "../hooks";

const PROPERTY_ID = 5;

const propertyFixture = {
  id: PROPERTY_ID,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [3, 4],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const holdFixture = {
  id: 9,
  property: PROPERTY_ID,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  reason: "owner_blocked",
};

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("useUpdatePropertyFeatures — BUG-018 over-invalidation narrowing", () => {
  it("writes the fresh detail into both id and slug keys without invalidating sibling sub-keys", async () => {
    server.use(
      http.patch(`/api/v1/properties/${PROPERTY_ID}`, () =>
        HttpResponse.json({ ...propertyFixture, feature_ids: [3, 4, 9] }),
      ),
    );
    // gcTime: Infinity so the seeded-but-unobserved sibling keys survive to
    // the assertion (the shared test client's gcTime: 0 collects them).
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity, staleTime: 0 },
        mutations: { retry: false },
      },
    });
    // Seed sibling sub-resources: a features-only edit must NOT blow them away.
    // ("NOT invalidated" needs seeded keys — getQueryState is undefined for
    // never-seeded keys.)
    const roomsKey = queryKeys.properties.rooms(PROPERTY_ID);
    const calendarKey = queryKeys.properties.availabilityCalendar(
      PROPERTY_ID,
      "2026-07-01",
      "2026-07-31",
    );
    // Routes key the detail query by id OR slug — feature_ids ride the
    // detail payload (there is no features sub-query), so BOTH variants must
    // receive the fresh payload for FeaturesTab/DetailsTab to settle.
    const detailByIdKey = queryKeys.properties.detail(PROPERTY_ID);
    const detailBySlugKey = queryKeys.properties.detail("casa-norte");
    queryClient.setQueryData(roomsKey, {});
    queryClient.setQueryData(calendarKey, {});
    queryClient.setQueryData(detailByIdKey, propertyFixture);
    queryClient.setQueryData(detailBySlugKey, propertyFixture);

    const { result } = renderHook(() => useUpdatePropertyFeatures(PROPERTY_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync([3, 4, 9]);

    await waitFor(() => {
      expect(
        queryClient.getQueryData<{ feature_ids: number[] }>(detailByIdKey)?.feature_ids,
      ).toEqual([3, 4, 9]);
    });
    expect(
      queryClient.getQueryData<{ feature_ids: number[] }>(detailBySlugKey)?.feature_ids,
    ).toEqual([3, 4, 9]);
    // Sibling sub-resources must NOT refetch — the detail prefix is not
    // invalidated, the payload is written directly.
    expect(queryClient.getQueryState(roomsKey)?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(calendarKey)?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(detailByIdKey)?.isInvalidated).toBe(false);
  });
});

describe("useArchiveProperty — BUG-018 over-invalidation narrowing", () => {
  it("invalidates the detail (id + slug) and the lists root, not the whole properties tree", async () => {
    server.use(
      http.post(`/api/v1/properties/${PROPERTY_ID}:archive`, () =>
        HttpResponse.json({ ...propertyFixture, status: "archived" }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useArchiveProperty({ id: PROPERTY_ID, slug: "casa-norte" }),
      { wrapper: wrapperFor(queryClient) },
    );

    await result.current.mutateAsync();

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.properties.detail(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.properties.detail("casa-norte"));
      expect(keys).toContainEqual(queryKeys.properties.lists());
      // The bare ["properties"] root would nuke every other property's detail.
      expect(keys).not.toContainEqual(queryKeys.properties.all());
    });
  });
});

describe("useCreatePropertyBlock — shared availability helper (BUG-018 m1)", () => {
  it("invalidates the property's availability, holds and bookings roots plus the cross-property tree", async () => {
    server.use(
      http.post(`/api/v1/properties/${PROPERTY_ID}/availability`, () =>
        HttpResponse.json(holdFixture, { status: 201 }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreatePropertyBlock(PROPERTY_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      reason: "owner_blocked",
    } as never);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.properties.availabilityRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.properties.holdsRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.properties.bookingsRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.availability.all());
    });
  });
});
