import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { leadStatusColorVar, type LeadStatus } from "@/styles/tokens";
import { leadStatusLabel } from "../schemas";

interface LeadStatusBadgeProps {
  value: LeadStatus;
  className?: string;
}

/**
 * Read-only lead-temperature pill: a coloured dot (keyed on the shared
 * `leadStatusColorVar` token, single source of truth with the schema enum) plus
 * the localised label. Unit 6 reuses this inside the inline edit cell.
 */
export function LeadStatusBadge({ value, className }: LeadStatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", className)}>
      <span
        className="size-2 rounded-full"
        style={{ backgroundColor: leadStatusColorVar[value] }}
        aria-hidden
      />
      {leadStatusLabel(value)}
    </Badge>
  );
}
