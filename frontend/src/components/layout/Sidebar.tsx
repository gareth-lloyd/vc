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
  prefetch?: () => Promise<unknown>;
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
              onMouseEnter={item.prefetch}
              onFocus={item.prefetch}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive
                    ? "bg-nav-active text-nav-active-foreground font-medium"
                    : "text-muted-foreground hover:bg-nav-hover hover:text-foreground",
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
    {
      to: "/enquiries",
      label: t("nav.enquiries"),
      icon: MessageSquare,
      prefetch: () => import("@/features/enquiries/EnquiriesListPage"),
    },
    {
      to: "/quotations",
      label: t("nav.quotes"),
      icon: FileText,
      prefetch: () => import("@/features/quotations/QuotationsListPage"),
    },
    {
      to: "/bookings",
      label: t("nav.bookings"),
      icon: CalendarCheck,
      prefetch: () => import("@/features/bookings/BookingsListPage"),
    },
  ];
  const library: NavItem[] = [
    {
      to: "/properties",
      label: t("nav.properties"),
      icon: Building2,
      prefetch: () => import("@/features/properties/PropertiesListPage"),
    },
    {
      to: "/contacts",
      label: t("nav.contacts"),
      icon: Users,
      prefetch: () => import("@/features/contacts/ContactsListPage"),
    },
  ];
  const admin: NavItem[] = [
    {
      to: "/admin/users",
      label: t("nav.users"),
      icon: UsersRound,
      prefetch: () => import("@/features/admin/users/UsersAdminPage"),
    },
    {
      to: "/admin/countries",
      label: t("nav.countries"),
      icon: Globe,
      prefetch: () => import("@/features/admin/countries/CountriesAdminPage"),
    },
    {
      to: "/admin/currencies",
      label: t("nav.currencies"),
      icon: Banknote,
      prefetch: () => import("@/features/admin/currencies/CurrenciesAdminPage"),
    },
    {
      to: "/admin/tags",
      label: t("nav.tags"),
      icon: Tags,
      prefetch: () => import("@/features/admin/tags/TagsAdminPage"),
    },
    {
      to: "/admin/system",
      label: t("nav.system"),
      icon: Settings,
      prefetch: () => import("@/features/admin/system/SystemAdminPage"),
    },
  ];

  return (
    <nav className="bg-card border-border w-60 shrink-0 border-r">
      <NavSection heading={t("nav.groups.operations")} items={operations} />
      <NavSection heading={t("nav.groups.library")} items={library} />
      {isAdmin && <NavSection heading={t("nav.groups.admin")} items={admin} />}
    </nav>
  );
}
