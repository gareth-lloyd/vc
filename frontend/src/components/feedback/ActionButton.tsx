import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type ButtonVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";

export interface ActionButtonProps {
  label: string;
  onClick: () => void;
  disableReason: string | null;
  // Optional: disable the button without surfacing a tooltip reason.
  // Useful while a precondition (e.g. line count) is still loading — the
  // button shouldn't be clickable, but "no lines" would be a lie.
  disabled?: boolean;
  variant?: ButtonVariant;
}

export function ActionButton({
  label,
  onClick,
  disableReason,
  disabled,
  variant = "outline",
}: ActionButtonProps) {
  const isDisabled = disableReason != null || disabled === true;
  const button = (
    <Button
      variant={variant}
      size="sm"
      className="w-full justify-start"
      onClick={onClick}
      disabled={isDisabled}
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
