import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/cn";

interface KpiCardProps {
  label: string;
  value: number | string | undefined;
  sublabel?: string;
  to: string;
  loading?: boolean;
  error?: boolean;
  errorLabel?: string;
}

export function KpiCard({ label, value, sublabel, to, loading, error, errorLabel }: KpiCardProps) {
  return (
    <Link
      to={to}
      className="hover:border-primary/40 focus-visible:ring-ring rounded-xl transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <Card className="gap-2 px-5 py-4">
        <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {label}
        </div>
        <div
          className={cn(
            "font-serif text-3xl font-semibold tracking-tight",
            error && "text-destructive font-sans text-sm font-normal",
            loading && "text-muted-foreground font-sans text-sm font-normal",
          )}
        >
          {error ? errorLabel : loading ? "—" : (value ?? "—")}
        </div>
        {sublabel ? <div className="text-muted-foreground text-xs">{sublabel}</div> : null}
      </Card>
    </Link>
  );
}
