import { useLocation } from "react-router-dom";

interface LocationState {
  next?: string;
}

const DEFAULT_NEXT = "/dashboard";

export function useNextPath(): string {
  const location = useLocation();
  const state = location.state as LocationState | null;
  return state?.next ?? DEFAULT_NEXT;
}
