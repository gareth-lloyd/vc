import { NavLink } from "react-router-dom";
import { Building2, CalendarCheck, Home } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export function OwnerSidebar() {
  const { t } = useTranslation("owner");

  const items: NavItem[] = [
    { to: "/owner/dashboard", label: t("nav.dashboard"), icon: Home },
    { to: "/owner/properties", label: t("nav.properties"), icon: Building2 },
    { to: "/owner/bookings", label: t("nav.bookings"), icon: CalendarCheck },
  ];

  return (
    <nav className="bg-sidebar text-sidebar-foreground border-sidebar-border w-56 shrink-0 border-r">
      <div className="border-sidebar-border border-b px-5 py-5">
        <span className="text-sidebar-foreground font-serif text-xl leading-none font-semibold">
          Villa Collective
        </span>
        <span className="text-sidebar-muted mt-1 block text-[11px] font-medium tracking-wider uppercase">
          {t("portal_label")}
        </span>
      </div>

      <ul className="space-y-0.5 px-3 pt-4">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
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
    </nav>
  );
}
