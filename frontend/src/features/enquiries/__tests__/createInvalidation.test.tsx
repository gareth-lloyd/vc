import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { invalidatedKeys } from "@/test/invalidation";
import { queryKeys } from "@/lib/query/keys";
import { useCreateEnquiry } from "../hooks";

// A minimal EnquiryDetail that parses cleanly through enquiryDetailSchema.
const enquiryFixture = {
  id: 7,
  reference: "E-XYZ-007",
  status: "new" as const,
  guest: null,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  phone: "",
  contact_method: null,
  property: 12,
  region: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 1,
  request_type: "quote" as const,
  assigned_to: null,
  agent: null,
  site_source: "main_website" as const,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  is_flexible: false,
  flexibility_days: 0,
  min_bedrooms: null,
  referral_code: "",
  inbound_message: "",
  quotations: [],
};

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useCreateEnquiry invalidations", () => {
  it("restains the status tab-bar badges (a new enquiry is always `new`)", async () => {
    server.use(http.post("/api/v1/enquiries", () => HttpResponse.json(enquiryFixture)));
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateEnquiry(), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync({} as never);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.enquiries.lists());
      expect(keys).toContainEqual(queryKeys.enquiries.statusCountsAll());
    });
  });
});
