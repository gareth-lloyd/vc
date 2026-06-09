import type { ReactElement } from "react";
import { useOwnerStore } from "./ownerStore";
import { OwnerProbeError } from "./OwnerProbeError";

// Both route guards (RequireOwner and RequireStaff) share one rule: an
// indeterminate owner-probe failure ("error") must render a retry, never a
// redirect. Centralise it here so the two guards can't diverge on probe-error
// handling. Returns the fallback element to render, or null to continue the
// guard's own idle/owner/not_owner decision.
export function useOwnerProbeFallback(): ReactElement | null {
  const ownerStatus = useOwnerStore((s) => s.status);
  return ownerStatus === "error" ? <OwnerProbeError /> : null;
}
