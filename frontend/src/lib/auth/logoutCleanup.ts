// Session-scoped state outside the auth feature (e.g. the owner-portal
// store) registers a cleanup here instead of auth importing the feature
// directly (GAP-063 — this inverts the auth→owner-portal edge). useLogout
// runs every registered cleanup alongside its own store/cache resets.
type LogoutCleanup = () => void;

const cleanups = new Set<LogoutCleanup>();

/** Register a cleanup to run on logout. Returns an unregister function. */
export function registerLogoutCleanup(cleanup: LogoutCleanup): () => void {
  cleanups.add(cleanup);
  return () => cleanups.delete(cleanup);
}

export function runLogoutCleanups(): void {
  for (const cleanup of cleanups) cleanup();
}
