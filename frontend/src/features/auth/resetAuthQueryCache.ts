import type { QueryClient } from "@tanstack/react-query";

// Single choke point for wiping cached server state at an auth boundary: login,
// 2FA verify, logout, and session-expiry 401. Every transition that crosses (or
// drops) a user identity MUST call this — otherwise it silently reintroduces the
// cross-user cache bleed this exists to prevent.
//
// Uses removeQueries rather than clear() so it never kicks a refetch on an
// observer still mounted during a 401 (which would re-hit the dead session and
// storm); for login/logout no observers are mounted, so the effect is identical.
export function resetAuthQueryCache(queryClient: QueryClient): void {
  queryClient.removeQueries();
}
