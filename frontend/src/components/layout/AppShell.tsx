import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { useAuthStore } from "@/features/auth/store";
import { useLogout } from "@/features/auth/hooks";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  return (
    <div className="bg-background flex h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar user={user} onSignOut={() => logout.mutate()} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
