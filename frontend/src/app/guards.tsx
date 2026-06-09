import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import { OwnerProbeError } from "@/features/owner-portal/OwnerProbeError";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";

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

// Gates the staff app (AppShell) tree. Staff pass through. A non-staff owner
// is bounced to their portal; anyone else lands on /login. The server is the
// real gate (every staff endpoint is staff-only) — this just keeps an owner
// from loading a staff shell that would only 403 on every call. Mirror of
// RequireOwner. Waits on both the auth and owner-probe boots (status "idle").
export function RequireStaff() {
  const authStatus = useAuthStore((s) => s.status);
  const isStaff = useAuthStore((s) => s.user?.is_staff ?? false);
  const ownerStatus = useOwnerStore((s) => s.status);

  if (authStatus === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }
  if (authStatus === "idle") {
    return null;
  }
  if (isStaff) {
    return <Outlet />;
  }
  // Non-staff: wait for the owner probe, then route owners to their portal.
  if (ownerStatus === "idle") {
    return null;
  }
  // An indeterminate probe failure (5xx/network) must not bounce a possible
  // owner to /login — offer a retry instead.
  if (ownerStatus === "error") {
    return <OwnerProbeError />;
  }
  return <Navigate to={ownerStatus === "owner" ? "/owner/dashboard" : "/login"} replace />;
}

export function RequireAdmin() {
  const status = useAuthStore((s) => s.status);
  const isAdmin = useHasAdminRole();
  const { t } = useTranslation("admin");

  const shouldRedirect = status === "authenticated" && !isAdmin;
  useEffect(() => {
    if (shouldRedirect) {
      toast.error(t("common.errors.admin_role_required_redirect"));
    }
  }, [shouldRedirect, t]);

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }
  if (status === "idle") return null;
  if (!isAdmin) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
