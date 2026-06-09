import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";

interface TabDef {
  to: string;
  label: string;
  /** Exact-match only, so the list tab isn't active on the nested quotes route. */
  end?: boolean;
}

/**
 * Route-linked tab strip for the Enquiries section: the enquiry list/board and
 * the cross-enquiry quotes pipeline (`/enquiries/quotes`). A `NavLink` strip —
 * not a `role="tablist"` — because each tab is a distinct route, not in-page
 * view state (the list's own Kanban/List toggle is the tablist).
 */
export function EnquiriesTabs() {
  const { t } = useTranslation("common");
  const tabs: TabDef[] = [
    { to: "/enquiries", label: t("nav.enquiries"), end: true },
    { to: "/enquiries/quotes", label: t("nav.quotes") },
  ];
  return (
    <nav className="border-border flex gap-1 border-b px-6" aria-label={t("nav.groups.operations")}>
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "border-foreground text-foreground"
                : "text-muted-foreground hover:text-foreground border-transparent",
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
