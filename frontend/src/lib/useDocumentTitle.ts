import { useEffect } from "react";

const APP_NAME = "Villa Collective";

/**
 * Keeps `document.title` in sync with the current page while mounted.
 *
 * Writes `\`${title} · Villa Collective\`` (or the bare app name when `title` is
 * empty, so a blank-title page never leaves the previous page's stale title).
 * There is intentionally no restore-on-unmount: the last mounted caller wins,
 * which is exactly the page the user is on. This assumes at most one caller is
 * mounted per screen — see the invariant note where it is used in `PageHeader`.
 */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
