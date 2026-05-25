import { Crown, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { tierColorVar, type Tier } from "@/styles/tokens";

interface TierBadgeProps {
  tier: Tier;
  label?: string;
  compact?: boolean;
  className?: string;
}

const TIER_ICON = {
  quintessential: Crown,
  signature: Sparkles,
} as const;

const TIER_LABEL = {
  quintessential: "Quintessential",
  signature: "Signature",
} as const;

export function TierBadge({ tier, label, compact = false, className }: TierBadgeProps) {
  const Icon = TIER_ICON[tier];
  const color = tierColorVar[tier];
  const text = label ?? TIER_LABEL[tier];
  return (
    <Badge
      variant="outline"
      className={cn("rounded-pill gap-1 font-medium", className)}
      style={{
        borderColor: `color-mix(in oklch, ${color} 50%, transparent)`,
        backgroundColor: `color-mix(in oklch, ${color} 10%, transparent)`,
        color,
      }}
    >
      <Icon className="size-3.5" aria-hidden />
      {compact ? <span>{text.charAt(0)}</span> : <span>{text}</span>}
    </Badge>
  );
}
