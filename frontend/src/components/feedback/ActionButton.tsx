import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type ButtonVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";

export interface ActionButtonProps {
  label: string;
  onClick: () => void;
  disableReason: string | null;
  variant?: ButtonVariant;
}

export function ActionButton({
  label,
  onClick,
  disableReason,
  variant = "outline",
}: ActionButtonProps) {
  const button = (
    <Button
      variant={variant}
      size="sm"
      className="w-full justify-start"
      onClick={onClick}
      disabled={disableReason != null}
    >
      {label}
    </Button>
  );
  if (disableReason == null) return button;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block">{button}</span>
      </TooltipTrigger>
      <TooltipContent>{disableReason}</TooltipContent>
    </Tooltip>
  );
}
