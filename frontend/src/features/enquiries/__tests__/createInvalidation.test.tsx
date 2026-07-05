import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/render";
import { server } from "@/test/msw/server";
import { invalidatedKeys } from "@/test/invalidation";
import { queryKeys } from "@/lib/query/keys";
import { useCloseEnquiry, useConvertEnquiry, useCreateEnquiry } from "../hooks";

// A minimal EnquiryDetail that parses cleanly through enquiryDetailSchema.
const enquiryFixture = {
  id: 7,
  reference: "E-XYZ-007",
  status: "new" as const,
  person: 42,
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

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useCreateEnquiry invalidations", () => {
  it("restains the status tab-bar badges (a new enquiry is always `new`)", async () => {
    server.use(http.post("/api/v1/enquiries", () => HttpResponse.json(enquiryFixture)));
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateEnquiry(), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync({} as never);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.enquiries.lists());
      expect(keys).toContainEqual(queryKeys.enquiries.statusCountsAll());
    });
  });

  it("invalidates the linked person's contact subtree (BUG-018)", async () => {
    server.use(http.post("/api/v1/enquiries", () => HttpResponse.json(enquiryFixture)));
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateEnquiry(), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync({} as never);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.contacts.detail(42));
      // agent is null — known no linked agent, so no broad fallback.
      expect(keys).not.toContainEqual(queryKeys.contacts.details());
    });
  });
});

describe("useCloseEnquiry invalidations (BUG-018)", () => {
  it("refreshes the linked person's contact subtree alongside lists/badges/dashboard", async () => {
    server.use(
      http.post("/api/v1/enquiries/7:close", () =>
        HttpResponse.json({ ...enquiryFixture, status: "dead" }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCloseEnquiry(7), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync({ lost_reason: "unknown" } as never);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.enquiries.lists());
      expect(keys).toContainEqual(queryKeys.enquiries.statusCountsAll());
      expect(keys).toContainEqual(queryKeys.contacts.detail(42));
    });
  });
});

describe("useConvertEnquiry invalidations (BUG-018)", () => {
  it("also refreshes the accepted quotation's detail, list and badges", async () => {
    server.use(
      http.post("/api/v1/enquiries/7:convert", () =>
        HttpResponse.json({ ...enquiryFixture, status: "converted" }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useConvertEnquiry(7), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync(55);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.quotations.detail(55));
      expect(keys).toContainEqual(queryKeys.quotations.lists());
      expect(keys).toContainEqual(queryKeys.quotations.statusCountsAll());
      expect(keys).toContainEqual(queryKeys.contacts.detail(42));
    });
  });
});
