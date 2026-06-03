import { create } from "zustand";
import type { OwnerMe, OwnerOrganisation } from "./schemas";

type OwnerStatus = "idle" | "owner" | "not_owner";

interface OwnerState {
  status: OwnerStatus;
  organisations: OwnerOrganisation[];
  setOwner: (me: OwnerMe) => void;
  setNotOwner: () => void;
  clear: () => void;
}

export const useOwnerStore = create<OwnerState>((set) => ({
  status: "idle",
  organisations: [],
  setOwner: (me) => set({ status: "owner", organisations: me.organisations }),
  setNotOwner: () => set({ status: "not_owner", organisations: [] }),
  clear: () => set({ status: "idle", organisations: [] }),
}));
