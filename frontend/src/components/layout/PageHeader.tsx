import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

interface Crumb {
  label: string;
  to?: string;
}

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  breadcrumbs?: Crumb[];
  actions?: ReactNode;
  className?: string;
  /** Optional eyebrow above the title — small muted uppercase label. */
  eyebrow?: ReactNode;
  /** Optional content below the subtitle (e.g. status/role badges). */
  meta?: ReactNode;
}

export function PageHeader({
  title,
  subtitle,
  breadcrumbs,
  actions,
  className,
  eyebrow,
  meta,
}: PageHeaderProps) {
  return (
    <header className={cn("relative px-6 pt-8 pb-6", className)}>
      {breadcrumbs?.length ? (
        <nav className="text-muted-foreground mb-2 flex items-center gap-1 text-xs">
          {breadcrumbs.map((crumb, i) => (
            <span key={`${crumb.label}-${i}`} className="flex items-center gap-1">
              {crumb.to ? (
                <Link to={crumb.to} className="hover:text-foreground hover:underline">
                  {crumb.label}
                </Link>
              ) : (
                <span>{crumb.label}</span>
              )}
              {i < breadcrumbs.length - 1 ? <ChevronRight className="size-3" /> : null}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow ? (
            <p className="text-muted-foreground mb-1 text-[11px] font-medium tracking-wider uppercase">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="text-foreground font-serif text-3xl leading-tight font-semibold">
            {title}
          </h1>
          {subtitle ? (
            <p className="text-muted-foreground mt-2 max-w-2xl text-sm">{subtitle}</p>
          ) : null}
          {meta ? <div className="mt-3">{meta}</div> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      <div className="border-border mt-6 border-b" aria-hidden />
    </header>
  );
}
