import type { ReactNode } from "react";

interface SectionProps {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function Section({ title, children, actions }: SectionProps) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-base font-semibold">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
