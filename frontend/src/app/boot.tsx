import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { authChannel } from "@/lib/api/authChannel";
import { useMe } from "@/features/auth/hooks";
import { useAuthStore } from "@/features/auth/store";
import { Skeleton } from "@/components/ui/skeleton";

const PUBLIC_PATH_PREFIX = "/login";

export function BootGate() {
  const location = useLocation();
  const isPublic = location.pathname.startsWith(PUBLIC_PATH_PREFIX);

  if (isPublic) return <Outlet />;
  return <AuthenticatedBoot />;
}

function AuthenticatedBoot() {
  const me = useMe();
  const status = useAuthStore((s) => s.status);
  const setUnauthenticated = useAuthStore((s) => s.setUnauthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (me.isError) setUnauthenticated();
  }, [me.isError, setUnauthenticated]);

  useEffect(() => {
    return authChannel.onUnauthorized(() => {
      const current = window.location.pathname + window.location.search;
      setUnauthenticated();
      if (!current.startsWith("/login")) {
        navigate("/login", { replace: true, state: { next: current } });
      }
    });
  }, [navigate, setUnauthenticated]);

  if (me.isPending && status === "idle") {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center p-8">
        <div className="w-full max-w-md space-y-3">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    );
  }

  return <Outlet />;
}
