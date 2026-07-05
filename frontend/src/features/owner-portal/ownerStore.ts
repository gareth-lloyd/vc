import { create } from "zustand";
import { registerLogoutCleanup } from "@/lib/auth/logoutCleanup";
import type { OwnerMe, OwnerOrganisation } from "./schemas";

// "error" is distinct from "not_owner": a non-owner is a 200 {is_owner:false}
// body (→ not_owner), whereas any probe *failure* (5xx/network/parse, including
// a 403) is indeterminate and must stay retryable rather than locking a genuine
// owner out of their portal for staleTime on a single transient blip.
type OwnerStatus = "idle" | "owner" | "not_owner" | "error";

interface OwnerState {
  status: OwnerStatus;
  organisations: OwnerOrganisation[];
  setOwner: (me: OwnerMe) => void;
  setNotOwner: () => void;
  setProbeError: () => void;
  clear: () => void;
}

export const useOwnerStore = create<OwnerState>((set) => ({
  status: "idle",
  organisations: [],
  setOwner: (me) => set({ status: "owner", organisations: me.organisations }),
  setNotOwner: () => set({ status: "not_owner", organisations: [] }),
  setProbeError: () => set({ status: "error", organisations: [] }),
  clear: () => set({ status: "idle", organisations: [] }),
}));

// Cleared on logout via the lib/auth registry rather than auth importing this
// feature (GAP-063). Module-scope registration is safe because this module is
// EAGERLY imported in every session (app/guards.tsx, app/boot.tsx, router's
// OwnerShell/RequireOwner) — if it ever becomes lazy, move the registration
// somewhere that still runs before logout.
registerLogoutCleanup(() => useOwnerStore.getState().clear());
