import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface QuickAction {
  label: string;
}

export function QuickActions({
  actions,
  tooltip = "Coming in next phase",
}: {
  actions: readonly QuickAction[];
  tooltip?: string;
}) {
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        Quick actions
      </p>
      {actions.map((a) => (
        <Tooltip key={a.label}>
          <TooltipTrigger asChild>
            <span className="block">
              <Button variant="outline" size="sm" className="w-full justify-start" disabled>
                {a.label}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
