import { useLocation } from "react-router-dom";

interface LocationState {
  next?: string;
}

const DEFAULT_NEXT = "/dashboard";

// A `next` value is only safe to navigate to if it is a same-origin relative
// path. Reject protocol-relative (`//evil.com`), absolute (`https://…`), and
// backslash-disguised URLs so `next` can never become an open redirect — even
// if a future caller wires it from a query param instead of internal state.
export function isSafeNextPath(next: string | undefined): next is string {
  return (
    typeof next === "string" &&
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.startsWith("/\\")
  );
}

export function useNextPath(): string {
  const location = useLocation();
  const state = location.state as LocationState | null;
  return isSafeNextPath(state?.next) ? state.next : DEFAULT_NEXT;
}
