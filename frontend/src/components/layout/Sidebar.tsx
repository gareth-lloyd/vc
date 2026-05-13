import { NavLink } from "react-router-dom";
import {
  Banknote,
  Building2,
  CalendarCheck,
  FileText,
  Globe,
  Home,
  MessageSquare,
  Settings,
  Tags,
  Users,
  UsersRound,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

function NavSection({ heading, items }: { heading: string; items: NavItem[] }) {
  return (
    <div className="px-3 py-2">
      <h2 className="text-muted-foreground px-3 pb-1 text-[11px] font-semibold tracking-wider uppercase">
        {heading}
      </h2>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4" aria-hidden />
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const { t } = useTranslation("common");
  const isAdmin = useHasAdminRole();

  const operations: NavItem[] = [
    { to: "/dashboard", label: t("nav.dashboard"), icon: Home },
    { to: "/enquiries", label: t("nav.enquiries"), icon: MessageSquare },
    { to: "/quotations", label: t("nav.quotes"), icon: FileText },
    { to: "/bookings", label: t("nav.bookings"), icon: CalendarCheck },
  ];
  const library: NavItem[] = [
    { to: "/properties", label: t("nav.properties"), icon: Building2 },
    { to: "/contacts", label: t("nav.contacts"), icon: Users },
  ];
  const admin: NavItem[] = [
    { to: "/admin/users", label: t("nav.users"), icon: UsersRound },
    { to: "/admin/countries", label: t("nav.countries"), icon: Globe },
    { to: "/admin/currencies", label: t("nav.currencies"), icon: Banknote },
    { to: "/admin/tags", label: t("nav.tags"), icon: Tags },
    { to: "/admin/system", label: t("nav.system"), icon: Settings },
  ];

  return (
    <nav className="bg-card border-border w-60 shrink-0 border-r">
      <NavSection heading={t("nav.groups.operations")} items={operations} />
      <NavSection heading={t("nav.groups.library")} items={library} />
      {isAdmin && <NavSection heading={t("nav.groups.admin")} items={admin} />}
    </nav>
  );
}
