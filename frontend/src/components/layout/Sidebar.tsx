import { NavLink } from "react-router-dom";
import {
  Banknote,
  Building2,
  CalendarCheck,
  ConciergeBell,
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

function triggerPrefetch(fn?: () => Promise<unknown>) {
  fn?.().catch(() => {});
}

function NavSection({ heading, items }: { heading: string; items: NavItem[] }) {
  return (
    <div className="px-3 pt-5 pb-2">
      <h2 className="text-sidebar-muted px-3 pb-2 text-[11px] font-medium tracking-wider uppercase">
        {heading}
      </h2>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              onMouseEnter={() => triggerPrefetch(item.prefetch)}
              onFocus={() => triggerPrefetch(item.prefetch)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-active text-sidebar-active-foreground font-medium"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-hover hover:text-sidebar-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    className={cn(
                      "size-4 transition-colors",
                      isActive ? "text-sidebar-active-foreground" : "text-sidebar-muted",
                    )}
                    aria-hidden
                  />
                  <span>{item.label}</span>
                </>
              )}
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
    {
      to: "/concierge",
      label: t("nav.concierge"),
      icon: ConciergeBell,
      prefetch: () => import("@/features/concierge/ConciergeOverviewPage"),
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
    <nav className="bg-sidebar text-sidebar-foreground border-sidebar-border w-64 shrink-0 border-r">
      <div className="border-sidebar-border border-b px-5 py-5">
        <span className="text-sidebar-foreground font-serif text-xl leading-none font-semibold">
          Villa Collective
        </span>
      </div>

      <NavSection heading={t("nav.groups.operations")} items={operations} />
      <NavSection heading={t("nav.groups.library")} items={library} />
      {isAdmin && <NavSection heading={t("nav.groups.admin")} items={admin} />}
    </nav>
  );
}
