import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BootGate } from "../boot";

function tree() {
  return (
    <Routes>
      <Route element={<BootGate />}>
        <Route path="/login" element={<div>LOGIN</div>} />
        <Route path="/dashboard" element={<div>STAFF AREA</div>} />
      </Route>
    </Routes>
  );
}

afterEach(() => {
  useAuthStore.getState().clear();
});

describe("boot CSRF prime", () => {
  it("primes the csrftoken cookie on a public-path boot (fresh browser at /login)", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/auth/csrf", () => {
        calls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(tree(), { route: "/login" });

    await waitFor(() => expect(calls).toBe(1));
  });

  it("still renders the route and warns when the prime request fails", async () => {
    server.use(http.get("/api/v1/auth/csrf", () => HttpResponse.error()));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      renderWithProviders(tree(), { route: "/login" });

      await waitFor(() => expect(document.body.textContent).toContain("LOGIN"));
      await waitFor(() => expect(warn).toHaveBeenCalled());
    } finally {
      warn.mockRestore();
    }
  });
});
