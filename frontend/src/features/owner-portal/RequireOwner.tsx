import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerStore } from "./ownerStore";

// Gates the /owner/* tree. Owners pass through. Staff are bounced to the staff
// app at /dashboard; everyone else lands on /login. Waits on both the auth and
// owner-probe boots resolving before deciding (status === "idle").
export function RequireOwner() {
  const authStatus = useAuthStore((s) => s.status);
  const isStaff = useAuthStore((s) => s.user?.is_staff ?? false);
  const ownerStatus = useOwnerStore((s) => s.status);

  if (authStatus === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }
  if (authStatus === "idle" || ownerStatus === "idle") {
    return null;
  }
  if (ownerStatus === "owner") {
    return <Outlet />;
  }
  // Authenticated but not an owner: staff go back to their app, others sign in.
  return <Navigate to={isStaff ? "/dashboard" : "/login"} replace />;
}
