import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authChannel } from "@/lib/api/authChannel";
import { resetAuthQueryCache } from "@/features/auth/resetAuthQueryCache";
import { primeCsrfCookie } from "@/lib/api/client";
import { useMe } from "@/features/auth/hooks";
import { useAuthStore } from "@/features/auth/store";
import { useOwnerMe } from "@/features/owner-portal/hooks";
import { useOwnerStore } from "@/features/owner-portal/ownerStore";
import { Skeleton } from "@/components/ui/skeleton";

// Paths reachable without a session. An anonymous visitor to any of these must
// NOT mount <AuthenticatedBoot> — that fires GET /auth/me → 401 → the
// onUnauthorized handler redirects to /login, which would bounce a reset-email
// link away before its form ever renders. The password-reset pages join /login.
const PUBLIC_PATH_PREFIXES = ["/login", "/forgot-password", "/reset-password"];

export function BootGate() {
  const location = useLocation();
  const isPublic = PUBLIC_PATH_PREFIXES.some((p) => location.pathname.startsWith(p));

  // Prime the csrftoken cookie once per boot so a fresh browser's first
  // unsafe request (typically the login POST itself) isn't 403'd by
  // CsrfViewMiddleware. Fire-and-forget — the API client also self-heals by
  // priming and replaying a CSRF-rejected request — but a failure here is
  // the early signal that the endpoint is broken, so it must not be silent.
  useEffect(() => {
    void primeCsrfCookie().then((ok) => {
      if (!ok) console.warn("csrf cookie prime failed; login may need a retry");
    });
  }, []);

  if (isPublic) return <Outlet />;
  return <AuthenticatedBoot />;
}

const ENROLL_PATH = "/enroll-2fa";

function AuthenticatedBoot() {
  const me = useMe();
  const status = useAuthStore((s) => s.status);
  const isStaff = useAuthStore((s) => s.user?.is_staff ?? false);
  const tfaMethod = useAuthStore((s) => s.user?.tfa_method ?? null);
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

  // Forced 2FA enrolment. Proactive (not just a 403 bounce): /auth/me already
  // carries tfa_method, so an unenrolled staff user is funnelled to /enroll-2fa
  // at boot — robust even on landing routes that fire no non-allowlisted query
  // (the owner probe's /owner/me is not on the enrolment allowlist and would
  // 403). The interceptor's emitEnrollmentRequired below is the fallback.
  useEffect(() => {
    if (status !== "authenticated") return;
    if (isStaff && tfaMethod === "none" && location.pathname !== ENROLL_PATH) {
      navigate(ENROLL_PATH, { replace: true });
    }
  }, [status, isStaff, tfaMethod, location.pathname, navigate]);

  useEffect(() => {
    return authChannel.onEnrollmentRequired(() => {
      if (window.location.pathname !== ENROLL_PATH) {
        navigate(ENROLL_PATH, { replace: true });
      }
    });
  }, [navigate]);

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
