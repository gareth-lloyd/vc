import { NavLink } from "react-router-dom";
import { Home, Building2, CalendarCheck, MessageSquare, Users } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const OPERATIONS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/enquiries", label: "Enquiries", icon: MessageSquare },
  { to: "/bookings", label: "Bookings", icon: CalendarCheck },
];
const LIBRARY: NavItem[] = [
  { to: "/properties", label: "Properties", icon: Building2 },
  { to: "/contacts", label: "Contacts", icon: Users },
];

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
  return (
    <nav className="bg-card border-border w-60 shrink-0 border-r">
      <NavSection heading="Operations" items={OPERATIONS} />
      <NavSection heading="Library" items={LIBRARY} />
    </nav>
  );
}
