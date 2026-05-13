import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  description = "We couldn't load this content. Try again.",
  onRetry,
  retrying,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "border-destructive/40 bg-destructive/5 rounded-lg border p-6 text-center",
        className,
      )}
      role="alert"
    >
      <h3 className="text-destructive text-base font-medium">{title}</h3>
      <p className="text-muted-foreground mt-1 text-sm">{description}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" disabled={retrying} onClick={onRetry}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      ) : null}
    </div>
  );
}
