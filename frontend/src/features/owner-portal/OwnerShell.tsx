import { Outlet } from "react-router-dom";
import { Topbar } from "@/components/layout/Topbar";
import { useAuthStore } from "@/features/auth/store";
import { useLogout } from "@/features/auth/hooks";
import { OwnerSidebar } from "./OwnerSidebar";

export function OwnerShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  return (
    <div className="bg-background flex h-screen">
      <OwnerSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar user={user} onSignOut={() => logout.mutate()} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
