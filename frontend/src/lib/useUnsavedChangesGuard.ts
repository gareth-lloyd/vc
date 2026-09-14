import { useCallback, useEffect, useMemo, useRef } from "react";
import { useBeforeUnload, useBlocker, type BlockerFunction } from "react-router-dom";

export interface UnsavedChangesGuard {
  /** True while an in-app navigation is held back and awaiting a decision. */
  blocked: boolean;
  /** Let the held navigation go through (the caller's unsaved state is discarded by unmount). */
  proceed: () => void;
  /** Cancel the held navigation and stay on the current route. */
  reset: () => void;
}

/**
 * Blocks in-app navigation (route change) and browser unload while `isDirty`.
 *
 * Renders no UI: the caller renders the stay/discard `ConfirmDialog` off
 * `blocked` and wires `proceed`/`reset` to its actions. Only pathname changes
 * are blocked, so same-route search-param updates are never intercepted.
 *
 * A pending block is released automatically when `isDirty` turns false (e.g.
 * a save completes behind the dialog) — React Router never resets a blocker
 * by itself.
 *
 * Constraints:
 * - React Router honours **one blocker per router** (last registered wins), so
 *   compose all dirty flags on a route into a single call — never stack guards.
 * - Requires a data router (`createBrowserRouter` / `createMemoryRouter`);
 *   tests use `renderWithDataRouter` from `@/test/render`.
 * - `beforeunload` is best-effort (the browser owns the prompt). Logout and
 *   session-expiry redirects are **not** guarded: the auth boundary unmounts
 *   the page before any navigation the blocker could see.
 */
export function useUnsavedChangesGuard(isDirty: boolean): UnsavedChangesGuard {
  const blocker = useBlocker(
    useCallback<BlockerFunction>(
      ({ currentLocation, nextLocation }) =>
        isDirty && currentLocation.pathname !== nextLocation.pathname,
      [isDirty],
    ),
  );

  // Each blocked navigation may be settled (proceed/reset) exactly once. The
  // router applies the resulting state inside a transition, so a second call
  // before that re-render lands (double-click on Discard, or Discard racing the
  // auto-reset below) would otherwise re-enter React Router's state machine and
  // throw "Invalid blocker state transition".
  const settled = useRef(false);
  useEffect(() => {
    if (blocker.state === "blocked") settled.current = false;
  }, [blocker.state]);
  const settle = useCallback(
    (action: "proceed" | "reset") => {
      if (blocker.state !== "blocked" || settled.current) return;
      settled.current = true;
      blocker[action]();
    },
    [blocker],
  );

  useEffect(() => {
    if (blocker.state === "blocked" && !isDirty) settle("reset");
  }, [blocker.state, isDirty, settle]);

  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (!isDirty) return;
        event.preventDefault();
        // Legacy browsers require a (deprecated) returnValue to show the prompt.
        event.returnValue = "";
      },
      [isDirty],
    ),
  );

  return useMemo(
    () => ({
      blocked: blocker.state === "blocked",
      proceed: () => settle("proceed"),
      reset: () => settle("reset"),
    }),
    [blocker.state, settle],
  );
}
