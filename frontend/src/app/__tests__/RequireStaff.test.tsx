import { afterEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import type { UserMe } from "@/features/auth/schemas";
import { RequireStaff } from "../guards";

function tree() {
  return (
    <Routes>
      <Route element={<RequireStaff />}>
        <Route path="/dashboard" element={<div>STAFF AREA</div>} />
      </Route>
      <Route path="/owner/dashboard" element={<div>OWNER PORTAL</div>} />
      <Route path="/login" element={<div>LOGIN</div>} />
    </Routes>
  );
}

function setAuth(status: "idle" | "authenticated" | "unauthenticated", isStaff: boolean) {
  useAuthStore.setState({ status, user: { is_staff: isStaff } as UserMe });
}

afterEach(() => {
  useAuthStore.setState({ status: "idle", user: null });
  useOwnerStore.setState({ status: "idle", organisations: [] });
});

describe("RequireStaff", () => {
  it("renders the staff area for a staff user", () => {
    setAuth("authenticated", true);
    useOwnerStore.setState({ status: "not_owner", organisations: [] });
    renderWithProviders(tree(), { route: "/dashboard" });
    expect(screenText()).toContain("STAFF AREA");
  });

  it("bounces a non-staff owner to the owner portal", () => {
    setAuth("authenticated", false);
    useOwnerStore.setState({ status: "owner", organisations: [] });
    renderWithProviders(tree(), { route: "/dashboard" });
    expect(screenText()).toContain("OWNER PORTAL");
  });

  it("sends an authenticated non-staff non-owner to login", () => {
    setAuth("authenticated", false);
    useOwnerStore.setState({ status: "not_owner", organisations: [] });
    renderWithProviders(tree(), { route: "/dashboard" });
    expect(screenText()).toContain("LOGIN");
  });

  it("redirects to login when unauthenticated", () => {
    setAuth("unauthenticated", false);
    renderWithProviders(tree(), { route: "/dashboard" });
    expect(screenText()).toContain("LOGIN");
  });
});

function screenText(): string {
  return document.body.textContent ?? "";
}
