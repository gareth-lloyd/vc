import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { useConfirmPropertyAvailability } from "../hooks";
import type { PropertyDetail } from "../schemas";

const PROPERTY_ID = 5;
const PROPERTY_SLUG = "casa-norte";

function makeDetail(overrides: Partial<PropertyDetail> = {}): PropertyDetail {
  return {
    id: PROPERTY_ID,
    name: "Casa Norte",
    display_name: "Casa Norte",
    slug: PROPERTY_SLUG,
    status: "active",
    channel: "direct",
    has_active_ical_feed: false,
    feature_ids: [],
    derived_feature_ids: [],
    availability_owner_updated_at: null,
    availability_confirmed_at: "2026-07-01T09:00:00Z",
    availability_confirmed_by_name: "Sam Staffer",
    calendar_last_imported_at: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
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

// Confirming refreshes both the property detail (the AvailabilityTab badges read
// off it) and the availability/timeline caches (Unit 7 surfaces the same badges).
const AFFECTED_KEYS = [
  queryKeys.properties.detail(PROPERTY_ID),
  queryKeys.properties.detail(PROPERTY_SLUG),
  queryKeys.properties.availabilityRoot(PROPERTY_ID),
  queryKeys.availability.all(),
] as const;

function seedAffectedKeys(client: QueryClient): void {
  for (const key of AFFECTED_KEYS) {
    client.setQueryData(key, {});
  }
}

afterEach(() => {
  server.resetHandlers();
});

describe("useConfirmPropertyAvailability", () => {
  it("POSTs the confirm-availability action and returns the updated detail", async () => {
    const client = createClient();
    seedAffectedKeys(client);

    let called = false;
    server.use(
      http.post(`/api/v1/properties/${PROPERTY_ID}:confirm-availability`, () => {
        called = true;
        return HttpResponse.json(makeDetail());
      }),
    );

    const { result } = renderHook(
      () => useConfirmPropertyAvailability({ id: PROPERTY_ID, slug: PROPERTY_SLUG }),
      { wrapper: wrapperWith(client) },
    );

    let returned: PropertyDetail | undefined;
    await act(async () => {
      returned = await result.current.mutateAsync();
    });

    expect(called).toBe(true);
    expect(returned?.availability_confirmed_by_name).toBe("Sam Staffer");
  });

  it("invalidates the detail and availability caches on success", async () => {
    const client = createClient();
    seedAffectedKeys(client);

    server.use(
      http.post(`/api/v1/properties/${PROPERTY_ID}:confirm-availability`, () =>
        HttpResponse.json(makeDetail()),
      ),
    );

    const { result } = renderHook(
      () => useConfirmPropertyAvailability({ id: PROPERTY_ID, slug: PROPERTY_SLUG }),
      { wrapper: wrapperWith(client) },
    );

    await act(async () => {
      await result.current.mutateAsync();
    });

    for (const key of AFFECTED_KEYS) {
      expect(client.getQueryState(key)?.isInvalidated, key.join("/")).toBe(true);
    }
  });
});
