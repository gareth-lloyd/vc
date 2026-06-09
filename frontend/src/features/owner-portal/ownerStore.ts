import { create } from "zustand";
import type { OwnerMe, OwnerOrganisation } from "./schemas";

// "error" is distinct from "not_owner": a 401/403 is a definitive "not an
// owner", but a 5xx/network probe failure is indeterminate and must stay
// retryable rather than locking a genuine owner out.
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
