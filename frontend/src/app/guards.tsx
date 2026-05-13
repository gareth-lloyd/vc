import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuthStore } from "@/features/auth/store";
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
