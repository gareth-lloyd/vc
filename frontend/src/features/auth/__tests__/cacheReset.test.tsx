import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { useAuthStore } from "../store";
import { useOwnerStore } from "../../owner-portal/ownerStore";
import { useLogin, useLogout, useVerifyTfa } from "../hooks";

// A query key that the old useLogout allowlist did NOT remove. The bug was that
// only auth.me/properties/bookings/owner were cleared, so a prior user's
// enquiries/contacts/etc. survived into the next session.
const LEAKY_KEY = queryKeys.enquiries.lists();

const fixtureUser = {
  id: 1,
  email: "ops@vc.test",
  first_name: "Ops",
  last_name: "User",
  phone: null,
  role: "operator",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  tfa_method: null,
  tfa_enrolled_at: null,
  last_login: null,
};

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // gcTime: Infinity so a seeded, observer-less key is removed ONLY by an
      // explicit cache reset — never by garbage collection. Otherwise the test
      // could pass for the wrong reason.
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

afterEach(() => {
  useAuthStore.getState().clear();
  useOwnerStore.getState().clear();
});

describe("auth boundaries reset the whole query cache", () => {
  it("useLogout removes a non-allowlisted key (no cross-user bleed)", async () => {
    server.use(http.post("/api/v1/auth/logout", () => new HttpResponse(null, { status: 204 })));
    const queryClient = makeClient();
    queryClient.setQueryData(LEAKY_KEY, [{ id: 99, leaked: true }]);

    const { result } = renderHook(() => useLogout(), { wrapper: wrapperFor(queryClient) });
    await result.current.mutateAsync();

    expect(queryClient.getQueryData(LEAKY_KEY)).toBeUndefined();
  });

  it("useLogin (no 2FA) clears a non-allowlisted key from the previous session", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: false, user: fixtureUser }),
      ),
    );
    const queryClient = makeClient();
    queryClient.setQueryData(LEAKY_KEY, [{ id: 99, leaked: true }]);

    const { result } = renderHook(() => useLogin(), { wrapper: wrapperFor(queryClient) });
    await result.current.mutateAsync({ email: "ops@vc.test", password: "secret" });

    await waitFor(() => expect(queryClient.getQueryData(LEAKY_KEY)).toBeUndefined());
  });

  it("useLogin (no 2FA) marks the store authenticated from the login payload", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: false, user: fixtureUser }),
      ),
    );
    const queryClient = makeClient();

    const { result } = renderHook(() => useLogin(), { wrapper: wrapperFor(queryClient) });
    await result.current.mutateAsync({ email: "ops@vc.test", password: "secret" });

    // The login response already carries the user — the store must flip to
    // "authenticated" synchronously, so the redirect doesn't lose the race
    // against the background useMe refetch (the "submit twice" bug).
    await waitFor(() => expect(useAuthStore.getState().status).toBe("authenticated"));
    expect(useAuthStore.getState().user?.email).toBe("ops@vc.test");
  });

  it("useLogin with 2FA required does NOT clear yet (challenge still pending)", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: true, challenge_token: "tok", expires_in_seconds: 300 }),
      ),
    );
    const queryClient = makeClient();
    queryClient.setQueryData(LEAKY_KEY, [{ id: 99, leaked: true }]);

    const { result } = renderHook(() => useLogin(), { wrapper: wrapperFor(queryClient) });
    await result.current.mutateAsync({ email: "ops@vc.test", password: "secret" });

    // The session is not yet established; clearing happens after the 2FA step.
    expect(queryClient.getQueryData(LEAKY_KEY)).toEqual([{ id: 99, leaked: true }]);
    expect(useAuthStore.getState().pendingTfa?.challengeToken).toBe("tok");
  });

  it("useVerifyTfa clears a non-allowlisted key from the previous session", async () => {
    server.use(
      http.post("/api/v1/auth/2fa:verify", () => HttpResponse.json({ user: fixtureUser })),
    );
    const queryClient = makeClient();
    queryClient.setQueryData(LEAKY_KEY, [{ id: 99, leaked: true }]);

    const { result } = renderHook(() => useVerifyTfa(), { wrapper: wrapperFor(queryClient) });
    await result.current.mutateAsync({ challenge_token: "tok", code: "123456" });

    await waitFor(() => expect(queryClient.getQueryData(LEAKY_KEY)).toBeUndefined());
  });
});
