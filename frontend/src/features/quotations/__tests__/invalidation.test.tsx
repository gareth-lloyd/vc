import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/render";
import { server } from "@/test/msw/server";
import { invalidatedKeys } from "@/test/invalidation";
import { queryKeys } from "@/lib/query/keys";
import {
  useConvertQuotation,
  useHoldQuotationLine,
  useSendQuotation,
  useWithdrawQuotation,
} from "../hooks";
import type { BookingDetail } from "@/features/bookings/schemas";

const QUOTATION_ID = 4;
const ENQUIRY_ID = 8;
const GUEST_ID = 7;
const AGENT_ID = 9;
const PROPERTY_ID = 12;

const quotationFixture = {
  id: QUOTATION_ID,
  reference: "Q-AAA-004",
  status: "sent",
  enquiry: ENQUIRY_ID,
  guest: GUEST_ID,
  agent: AGENT_ID,
};

const bookingFixture = {
  id: 51,
  reference: "B-AAA-001",
  status: "awaiting_deposit",
  property: PROPERTY_ID,
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
};

const lineFixture = {
  id: 5,
  quotation: QUOTATION_ID,
  property: PROPERTY_ID,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  hold: { id: 1, date_from: "2026-07-01", date_to: "2026-07-08", expires_at: null },
};

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("useConvertQuotation — BUG-018 cross-entity fan-out", () => {
  it("invalidates the quotation, its parent enquiry, both contacts, booking lists and the property's availability", async () => {
    server.use(
      http.post(`/api/v1/quotations/${QUOTATION_ID}:convert`, () =>
        HttpResponse.json(bookingFixture),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useConvertQuotation(quotationFixture), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ line: 5, terms_accepted: true });

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.quotations.detail(QUOTATION_ID));
      expect(keys).toContainEqual(queryKeys.quotations.lists());
      expect(keys).toContainEqual(queryKeys.quotations.statusCountsAll());
      expect(keys).toContainEqual(queryKeys.enquiries.detail(ENQUIRY_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(GUEST_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(AGENT_ID));
      expect(keys).toContainEqual(queryKeys.bookings.lists());
      expect(keys).toContainEqual(queryKeys.properties.availabilityRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.availability.all());
      // The enquiry status flips to CONVERTED server-side.
      expect(keys).toContainEqual(queryKeys.enquiries.lists());
      expect(keys).toContainEqual(queryKeys.enquiries.statusCountsAll());
    });
  });

  it("primes the new booking's detail cache from the response", async () => {
    server.use(
      http.post(`/api/v1/quotations/${QUOTATION_ID}:convert`, () =>
        HttpResponse.json(bookingFixture),
      ),
    );
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useConvertQuotation(quotationFixture), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ line: 5, terms_accepted: true });

    const cached = queryClient.getQueryData<BookingDetail>(queryKeys.bookings.detail(51));
    expect(cached?.reference).toBe("B-AAA-001");
  });
});

describe("useSendQuotation — BUG-018 cross-entity fan-out", () => {
  it("invalidates the parent enquiry and the guest's contact subtree (precise, not broad)", async () => {
    server.use(
      http.post(`/api/v1/quotations/${QUOTATION_ID}:send`, () =>
        HttpResponse.json({ ...quotationFixture, agent: null }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSendQuotation(QUOTATION_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync(undefined);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.enquiries.detail(ENQUIRY_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(GUEST_ID));
      expect(keys).not.toContainEqual(queryKeys.contacts.details());
    });
  });
});

describe("useWithdrawQuotation — BUG-018 cross-entity fan-out", () => {
  it("invalidates the quotation status keys plus the enquiry and contact subtrees", async () => {
    server.use(
      http.post(`/api/v1/quotations/${QUOTATION_ID}:withdraw`, () =>
        HttpResponse.json({ ...quotationFixture, status: "cancelled" }),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useWithdrawQuotation(QUOTATION_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync("changed mind");

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.quotations.detail(QUOTATION_ID));
      expect(keys).toContainEqual(queryKeys.quotations.lists());
      expect(keys).toContainEqual(queryKeys.quotations.statusCountsAll());
      expect(keys).toContainEqual(queryKeys.enquiries.detail(ENQUIRY_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(GUEST_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(AGENT_ID));
    });
  });
});

describe("useHoldQuotationLine — BUG-018 availability fan-out", () => {
  it("invalidates the held line's property availability + related enquiry/contacts, without status churn", async () => {
    server.use(
      http.post(`/api/v1/quotations/${QUOTATION_ID}/lines/5:hold`, () =>
        HttpResponse.json(lineFixture),
      ),
    );
    const queryClient = createTestQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useHoldQuotationLine(QUOTATION_ID, quotationFixture), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync(5);

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      // detail(id) prefix-covers the lines sub-key.
      expect(keys).toContainEqual(queryKeys.quotations.detail(QUOTATION_ID));
      expect(keys).toContainEqual(queryKeys.properties.availabilityRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.properties.holdsRoot(PROPERTY_ID));
      expect(keys).toContainEqual(queryKeys.availability.all());
      expect(keys).toContainEqual(queryKeys.enquiries.detail(ENQUIRY_ID));
      expect(keys).toContainEqual(queryKeys.contacts.detail(GUEST_ID));
      // A hold is not a status transition — no list/badge churn.
      expect(keys).not.toContainEqual(queryKeys.quotations.lists());
      expect(keys).not.toContainEqual(queryKeys.quotations.statusCountsAll());
    });
  });
});
