import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import { BootGate } from "../boot";

const STAFF_UNENROLLED = {
  id: 1,
  email: "ops@vc.test",
  first_name: "Ops",
  last_name: "User",
  phone: null,
  role: "operator",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  tfa_method: "none",
  tfa_enrolled_at: null,
  last_login: null,
  preferred_language: "en",
};

function authenticatedAs(user: typeof STAFF_UNENROLLED) {
  server.use(
    http.get("/api/v1/auth/me", () => HttpResponse.json(user)),
    http.get("/api/v1/auth/permissions", () =>
      HttpResponse.json({ role: user.role, is_superuser: false, permissions: [] }),
    ),
    http.get("/api/v1/owner/me", () =>
      HttpResponse.json({ user, is_owner: false, organisations: [] }),
    ),
  );
}

function tree() {
  return (
    <Routes>
      <Route element={<BootGate />}>
        <Route path="/dashboard" element={<div>STAFF AREA</div>} />
        <Route path="/enroll-2fa" element={<div>ENROL 2FA</div>} />
      </Route>
    </Routes>
  );
}

afterEach(() => {
  useAuthStore.getState().clear();
  useOwnerStore.getState().clear();
});

describe("boot 2FA enrolment redirect", () => {
  it("funnels an unenrolled staff user to /enroll-2fa", async () => {
    authenticatedAs(STAFF_UNENROLLED);
    renderWithProviders(tree(), { route: "/dashboard" });

    await waitFor(() => expect(document.body.textContent).toContain("ENROL 2FA"));
  });

  it("leaves an enrolled staff user on their landing route", async () => {
    authenticatedAs({ ...STAFF_UNENROLLED, tfa_method: "totp" });
    renderWithProviders(tree(), { route: "/dashboard" });

    await waitFor(() => expect(document.body.textContent).toContain("STAFF AREA"));
    expect(document.body.textContent).not.toContain("ENROL 2FA");
  });
});
