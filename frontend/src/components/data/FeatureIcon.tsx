import type { ComponentType, SVGProps } from "react";
import { Tag } from "lucide-react";
import { DynamicIcon, iconNames, type IconName } from "lucide-react/dynamic";
import { cn } from "@/lib/cn";

const ICON_NAME_SET: ReadonlySet<string> = new Set(iconNames);

/** Type guard: is `name` a renderable lucide icon name? */
function isIconName(name: string | null | undefined): name is IconName {
  return name != null && ICON_NAME_SET.has(name);
}

interface FeatureIconProps {
  /** A lucide icon name (kebab-case). Empty / unknown names render the fallback. */
  name?: string | null;
  className?: string;
  /** Rendered when `name` is empty or not a valid lucide name. `null` renders nothing. */
  fallback?: ComponentType<SVGProps<SVGSVGElement>> | null;
}

/**
 * Renders a lucide icon by name. The stored `Feature.icon` / `FeatureCategory.icon`
 * value is a kebab-case lucide name; this resolves it via `DynamicIcon` (lazy, no
 * bundle bloat) and falls back gracefully for blank or legacy/unknown values.
 */
export function FeatureIcon({ name, className, fallback = Tag }: FeatureIconProps) {
  if (isIconName(name)) {
    return <DynamicIcon name={name} className={cn("size-4", className)} aria-hidden />;
  }
  if (fallback === null) return null;
  const Fallback = fallback;
  return <Fallback className={cn("size-4", className)} aria-hidden />;
}
