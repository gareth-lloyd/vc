import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authChannel } from "@/lib/api/authChannel";
import { resetAuthQueryCache } from "@/features/auth/resetAuthQueryCache";
import { primeCsrf } from "@/features/auth/api";
import { useMe } from "@/features/auth/hooks";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerMe } from "@/features/owner-portal/hooks";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import { Skeleton } from "@/components/ui/skeleton";

const PUBLIC_PATH_PREFIX = "/login";

export function BootGate() {
  const location = useLocation();
  const isPublic = location.pathname.startsWith(PUBLIC_PATH_PREFIX);

  // Prime the csrftoken cookie once per boot so a fresh browser's first
  // unsafe request (typically the login POST itself) isn't 403'd by
  // CsrfViewMiddleware. Fire-and-forget: a failure degrades to the
  // pre-prime behaviour, it must never block rendering.
  useEffect(() => {
    primeCsrf().catch(() => {});
  }, []);

  if (isPublic) return <Outlet />;
  return <AuthenticatedBoot />;
}

function AuthenticatedBoot() {
  const me = useMe();
  const status = useAuthStore((s) => s.status);
  const isStaff = useAuthStore((s) => s.user?.is_staff ?? false);
  const setUnauthenticated = useAuthStore((s) => s.setUnauthenticated);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Probe owner status once authenticated. Non-staff users are the common
  // owner case, but staff can also be owners — probe regardless and let the
  // store record the outcome.
  useOwnerMe(status === "authenticated");
  const ownerStatus = useOwnerStore((s) => s.status);

  // Route owners to their portal. They go there from the app root and bare
  // /owner. A non-staff owner has no staff app to use, so the staff root and
  // dashboard also funnel them to /owner/dashboard. Staff owners keep their
  // staff landing and reach the portal explicitly via /owner.
  useEffect(() => {
    if (ownerStatus !== "owner") return;
    const path = location.pathname;
    const ownerLanding = path === "/" || path === "/owner" || path === "/owner/";
    const staffLandingForNonStaff = !isStaff && path === "/dashboard";
    if (ownerLanding || staffLandingForNonStaff) {
      navigate("/owner/dashboard", { replace: true });
    }
  }, [ownerStatus, isStaff, location.pathname, navigate]);

  useEffect(() => {
    if (me.isError) setUnauthenticated();
  }, [me.isError, setUnauthenticated]);

  useEffect(() => {
    return authChannel.onUnauthorized(() => {
      const current = window.location.pathname + window.location.search;
      // Flip auth state and navigate away from the protected tree FIRST, then
      // reset the cache. Resetting while the staff shell is still mounted would
      // make every active query refetch against the dead session (another 401 →
      // storm), which is why resetAuthQueryCache uses removeQueries rather than
      // clear — it drops cached data without kicking a refetch.
      setUnauthenticated();
      useOwnerStore.getState().clear();
      if (!current.startsWith("/login")) {
        navigate("/login", { replace: true, state: { next: current } });
      }
      resetAuthQueryCache(queryClient);
    });
  }, [navigate, setUnauthenticated, queryClient]);

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
