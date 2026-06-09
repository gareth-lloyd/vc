import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { queryKeys } from "@/lib/query/keys";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import { BootGate } from "../boot";

const LEAKY_KEY = queryKeys.enquiries.lists();

function tree() {
  return (
    <Routes>
      <Route element={<BootGate />}>
        <Route path="/dashboard" element={<div>STAFF AREA</div>} />
      </Route>
      <Route path="/login" element={<div>LOGIN</div>} />
    </Routes>
  );
}

afterEach(() => {
  useAuthStore.getState().clear();
  useOwnerStore.getState().clear();
});

describe("boot 401 handler", () => {
  it("on a session-expiry 401: redirects to /login and drops the previous session's cache", async () => {
    // Default MSW handler returns 401 for /auth/me; that fires authChannel.
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({ detail: "Unauthenticated" }, { status: 401 }),
      ),
    );
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity, staleTime: 0 },
        mutations: { retry: false },
      },
    });
    queryClient.setQueryData(LEAKY_KEY, [{ id: 99, leaked: true }]);

    renderWithProviders(tree(), { route: "/dashboard", queryClient });

    await waitFor(() => expect(document.body.textContent).toContain("LOGIN"));
    expect(queryClient.getQueryData(LEAKY_KEY)).toBeUndefined();
    expect(useOwnerStore.getState().status).toBe("idle");
  });
});
