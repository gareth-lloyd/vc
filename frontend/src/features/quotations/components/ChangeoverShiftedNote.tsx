import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";

interface Props {
  // The original arrival the stay was shifted away from (GAP-007). Null/absent
  // when the dates weren't moved — nothing renders in that case.
  from: string | null | undefined;
  className?: string;
}

// Inline "we moved your dates" hint shown wherever a shifted stay's dates are
// rendered (builder, convert dialog, quotation detail). Kept in one place so
// the copy and styling stay in lockstep across those surfaces.
export function ChangeoverShiftedNote({ from, className }: Props) {
  const { t } = useTranslation("quotations");
  if (!from) return null;
  return (
    <span className={cn("text-muted-foreground block text-xs", className)}>
      {t("notes.changeover_shifted", { from: formatDate(from) })}
    </span>
  );
}
