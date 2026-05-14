import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";

interface ToolbarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  searchAriaLabel?: string;
  filters?: ReactNode;
  rightSlot?: ReactNode;
  className?: string;
}

export function Toolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  searchAriaLabel,
  filters,
  rightSlot,
  className,
}: ToolbarProps) {
  const { t } = useTranslation("common");
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="relative max-w-xs flex-1">
        <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <Input
          type="search"
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder ?? t("search.placeholder")}
          className="pl-8"
          aria-label={searchAriaLabel ?? t("search.aria_label")}
        />
      </div>
      {filters}
      {rightSlot ? <div className="ml-auto">{rightSlot}</div> : null}
    </div>
  );
}
