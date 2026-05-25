import { cn } from "@/lib/cn";
import { serviceColorVar, type ServiceKey } from "@/styles/tokens";

/**
 * The six concierge service states from mock_up_analysis/01-new-res-system.md
 * §2.7. Each maps to a fill style on top of the service's brand colour ring.
 */
export const SERVICE_STATUSES = [
  "not_started",
  "working_on_it",
  "waiting",
  "arranged_independently",
  "not_required",
  "done",
] as const;

export type ServiceStatus = (typeof SERVICE_STATUSES)[number];

interface ServiceDotProps {
  service: ServiceKey;
  status?: ServiceStatus;
  size?: "sm" | "md";
  className?: string;
  /**
   * Localised accessible label, e.g. `t("services.chef") + " — " +
   * t("serviceStatus.working_on_it")`. Required so screen readers never
   * hear untranslated enum keys.
   */
  label: string;
}

const SIZE_CLASSES = {
  sm: "size-2.5 border",
  md: "size-3.5 border-2",
} as const;

export function ServiceDot({
  service,
  status = "not_started",
  size = "md",
  className,
  label,
}: ServiceDotProps) {
  const ringColor = serviceColorVar[service];
  const fill = fillFor(status, ringColor);
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn("inline-block rounded-full", SIZE_CLASSES[size], className)}
      style={{ borderColor: ringColor, backgroundColor: fill }}
    />
  );
}

function fillFor(status: ServiceStatus, ringColor: string): string {
  switch (status) {
    case "done":
      return ringColor;
    case "working_on_it":
      return `color-mix(in oklch, ${ringColor} 50%, transparent)`;
    case "waiting":
      return `color-mix(in oklch, ${ringColor} 20%, transparent)`;
    case "arranged_independently":
      return "transparent";
    case "not_required":
      return "var(--muted)";
    case "not_started":
    default:
      return "var(--background)";
  }
}
