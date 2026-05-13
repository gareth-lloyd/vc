import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/features/auth/store";

export function RequireAuth() {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  if (status === "unauthenticated") {
    const next = location.pathname + location.search;
    return <Navigate to="/login" replace state={{ next }} />;
  }
  if (status === "authenticated") {
    return <Outlet />;
  }
  return null;
}
