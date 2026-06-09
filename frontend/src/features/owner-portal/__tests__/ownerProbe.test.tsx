import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { RequireStaff } from "@/app/guards";
import { useOwnerStore } from "../ownerStore";
import { useOwnerMe } from "../hooks";
import { RequireOwner } from "../RequireOwner";

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

afterEach(() => {
  useAuthStore.setState({ status: "idle", user: null });
  useOwnerStore.getState().clear();
});

describe("useOwnerMe terminal store state", () => {
  it("a 403 resolves to not_owner (a definitive non-owner)", async () => {
    server.use(http.get("/api/v1/owner/me", () => HttpResponse.json({}, { status: 403 })));
    const { unmount } = renderHook(() => useOwnerMe(true), { wrapper: wrapperFor(makeClient()) });
    await waitFor(() => expect(useOwnerStore.getState().status).toBe("not_owner"));
    unmount();
  });

  it("a 500 resolves to error (retryable), NOT not_owner — no 5-minute lockout", async () => {
    server.use(http.get("/api/v1/owner/me", () => HttpResponse.json({}, { status: 500 })));
    const { unmount } = renderHook(() => useOwnerMe(true), { wrapper: wrapperFor(makeClient()) });
    await waitFor(() => expect(useOwnerStore.getState().status).toBe("error"));
    unmount();
  });
});

describe("guards treat a probe error as retryable, not a redirect", () => {
  function ownerTree() {
    return (
      <Routes>
        <Route element={<RequireOwner />}>
          <Route path="/owner/dashboard" element={<div>OWNER PORTAL</div>} />
        </Route>
        <Route path="/login" element={<div>LOGIN</div>} />
      </Routes>
    );
  }

  function staffTree() {
    return (
      <Routes>
        <Route element={<RequireStaff />}>
          <Route path="/dashboard" element={<div>STAFF AREA</div>} />
        </Route>
        <Route path="/login" element={<div>LOGIN</div>} />
      </Routes>
    );
  }

  it("RequireOwner shows a retry state on probe error, not /login", () => {
    useAuthStore.setState({ status: "authenticated", user: { is_staff: false } as UserMe });
    useOwnerStore.setState({ status: "error", organisations: [] });
    renderWithProviders(ownerTree(), { route: "/owner/dashboard" });
    expect(document.body.textContent).not.toContain("LOGIN");
    expect(document.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("RequireStaff (non-staff) shows a retry state on probe error, not /login", () => {
    useAuthStore.setState({ status: "authenticated", user: { is_staff: false } as UserMe });
    useOwnerStore.setState({ status: "error", organisations: [] });
    renderWithProviders(staffTree(), { route: "/dashboard" });
    expect(document.body.textContent).not.toContain("LOGIN");
    expect(document.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("RequireStaff still routes a staff user straight through, ignoring owner status", () => {
    useAuthStore.setState({ status: "authenticated", user: { is_staff: true } as UserMe });
    useOwnerStore.setState({ status: "error", organisations: [] });
    renderWithProviders(staffTree(), { route: "/dashboard" });
    expect(document.body.textContent).toContain("STAFF AREA");
  });
});
