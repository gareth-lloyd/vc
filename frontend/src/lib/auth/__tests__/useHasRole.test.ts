import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuthStore } from "@/features/auth/store";
import { useHasAccountsRole, useHasReservationsRole } from "../useHasRole";
import type { UserMe } from "@/features/auth/schemas";

function makeUser(overrides: Partial<UserMe> = {}): UserMe {
  return {
    id: 1,
    email: "a@b.com",
    first_name: "A",
    last_name: "B",
    is_active: true,
    is_staff: false,
    is_superuser: false,
    preferred_language: "en",
    ...overrides,
  };
}

beforeEach(() => {
  useAuthStore.getState().clear();
});

describe("useHasReservationsRole", () => {
  // The PermissionsView returns `User.role` verbatim, and that value is the
  // LOWERCASE `core.enums.StaffRole` `.value` ("admin"/"reservations"/…). These
  // feed the real lowercase wire value — an uppercase-only set would be
  // superuser-only in production (the latent bug this hook used to have).
  it("returns true for the lowercase 'admin' wire value", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "admin",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(true);
  });

  it("returns true for the lowercase 'reservations' wire value", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "reservations",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(true);
  });

  it("is case-insensitive (tolerates an uppercase role value)", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "RESERVATIONS",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(true);
  });

  it("returns true for a superuser regardless of role", () => {
    useAuthStore.getState().setMe(makeUser({ is_superuser: true }), {
      role: "VIEWER",
      is_superuser: true,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(true);
  });

  it("returns false for VIEWER / ACCOUNTS", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "VIEWER",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(false);
  });

  it("returns false when unauthenticated / no role", () => {
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(false);
  });

  it("reacts to store updates", () => {
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(false);
    act(() => {
      useAuthStore.getState().setMe(makeUser(), {
        role: "RESERVATIONS",
        is_superuser: false,
        permissions: [],
      });
    });
    expect(result.current).toBe(true);
  });
});

describe("useHasAccountsRole", () => {
  // The PermissionsView returns `User.role` verbatim, and that value is the
  // LOWERCASE `core.enums.StaffRole` `.value` ("accounts"/"admin"/…). These
  // tests feed the real lowercase wire value — the hook must match it (an
  // uppercase-only set, as the reservations hook uses, would be superuser-only
  // in production).
  it("returns true for the lowercase 'accounts' wire value", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "accounts",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasAccountsRole());
    expect(result.current).toBe(true);
  });

  it("returns true for the lowercase 'admin' wire value", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "admin",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasAccountsRole());
    expect(result.current).toBe(true);
  });

  it("returns true for a superuser regardless of role", () => {
    useAuthStore.getState().setMe(makeUser({ is_superuser: true }), {
      role: "viewer",
      is_superuser: true,
      permissions: [],
    });
    const { result } = renderHook(() => useHasAccountsRole());
    expect(result.current).toBe(true);
  });

  it("returns false for viewer / reservations", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "reservations",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasAccountsRole());
    expect(result.current).toBe(false);
  });

  it("returns false when unauthenticated / no role", () => {
    const { result } = renderHook(() => useHasAccountsRole());
    expect(result.current).toBe(false);
  });
});
