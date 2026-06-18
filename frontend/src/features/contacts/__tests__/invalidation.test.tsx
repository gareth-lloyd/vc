import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import {
  useCreateContact,
  useCreateContactEmail,
  useDeleteContactPhone,
  useSetPrimaryContactEmail,
  useUpdateContact,
} from "../hooks";

const CONTACT_ID = 7;

const contactFixture = {
  id: CONTACT_ID,
  kind: "person",
  display_name: "Jane Doe",
  first_name: "Jane",
  last_name: "Doe",
  company_name: null,
  status: "active",
  notes: "",
  emails: [],
  phones: [],
  primary_email: null,
  primary_phone: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const emailFixture = {
  id: 1,
  email: "jane@vc.test",
  label: null,
  is_primary: true,
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

function invalidatedKeys(spy: { mock: { calls: unknown[][] } }): unknown[] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown }).queryKey);
}

afterEach(() => vi.restoreAllMocks());

describe("contact mutations invalidate the list (list rows carry email/phone)", () => {
  it("useCreateContact invalidates the contacts list", async () => {
    server.use(http.post("/api/v1/contacts", () => HttpResponse.json(contactFixture)));
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateContact(), { wrapper: wrapperFor(queryClient) });

    await result.current.mutateAsync({
      first_name: "Jane",
      last_name: "Doe",
      emails: [{ email: "jane@vc.test", is_primary: true }],
    });

    await waitFor(() => expect(invalidatedKeys(spy)).toContainEqual(queryKeys.contacts.lists()));
  });

  it("useUpdateContact invalidates both the detail and the list", async () => {
    server.use(
      http.patch(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
    );
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useUpdateContact(CONTACT_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ first_name: "Janet" });

    await waitFor(() => {
      const keys = invalidatedKeys(spy);
      expect(keys).toContainEqual(queryKeys.contacts.detail(CONTACT_ID));
      expect(keys).toContainEqual(queryKeys.contacts.lists());
    });
  });

  it("useSetPrimaryContactEmail invalidates the list", async () => {
    server.use(
      http.post(`/api/v1/contacts/${CONTACT_ID}/emails/1:set-primary`, () =>
        HttpResponse.json(emailFixture),
      ),
    );
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSetPrimaryContactEmail(CONTACT_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ emailId: 1 });

    await waitFor(() => expect(invalidatedKeys(spy)).toContainEqual(queryKeys.contacts.lists()));
  });

  it("useCreateContactEmail invalidates the list", async () => {
    server.use(
      http.post(`/api/v1/contacts/${CONTACT_ID}/emails`, () => HttpResponse.json(emailFixture)),
    );
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateContactEmail(CONTACT_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ email: "x@vc.test" } as never);

    await waitFor(() => expect(invalidatedKeys(spy)).toContainEqual(queryKeys.contacts.lists()));
  });

  it("useDeleteContactPhone invalidates the list", async () => {
    server.use(
      http.delete(
        `/api/v1/contacts/${CONTACT_ID}/phones/2`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    const queryClient = makeClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useDeleteContactPhone(CONTACT_ID), {
      wrapper: wrapperFor(queryClient),
    });

    await result.current.mutateAsync({ phoneId: 2 });

    await waitFor(() => expect(invalidatedKeys(spy)).toContainEqual(queryKeys.contacts.lists()));
  });
});
