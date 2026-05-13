import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuthStore } from "@/features/auth/store";
import { useHasReservationsRole } from "../useHasRole";
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
    ...overrides,
  };
}

beforeEach(() => {
  useAuthStore.getState().clear();
});

describe("useHasReservationsRole", () => {
  it("returns true for ADMIN", () => {
    useAuthStore.getState().setMe(makeUser(), {
      role: "ADMIN",
      is_superuser: false,
      permissions: [],
    });
    const { result } = renderHook(() => useHasReservationsRole());
    expect(result.current).toBe(true);
  });

  it("returns true for RESERVATIONS", () => {
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
