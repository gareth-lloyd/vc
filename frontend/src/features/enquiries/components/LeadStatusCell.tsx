import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { cn } from "@/lib/cn";
import { LEAD_STATUSES, leadStatusColorVar } from "@/styles/tokens";
import type { LeadStatus } from "@/styles/tokens";
import { useSetLeadStatus } from "../hooks";
import { leadStatusLabel } from "../schemas";
import { LeadStatusBadge } from "./LeadStatusBadge";

interface LeadStatusCellProps {
  enquiryId: number;
  reference: string;
  value: LeadStatus;
}

/**
 * Inline lead-temperature picker for the list table — mirrors the concierge
 * `ServiceStatusCell` (Popover + per-cell audited mutation). Without the
 * reservations role it collapses to the read-only badge. The trigger stops
 * click propagation because `DataTable` rows navigate on click; the popover
 * itself is portalled, so its options never reach the row.
 */
export function LeadStatusCell({ enquiryId, reference, value }: LeadStatusCellProps) {
  const { t } = useTranslation("enquiries");
  const [open, setOpen] = useState(false);
  const canWrite = useHasReservationsRole();
  const setLeadStatus = useSetLeadStatus(enquiryId);

  if (!canWrite) {
    // Per CLAUDE.md role-gating: the affordance stays visible but inert, with a
    // Tooltip explaining why (mirrors concierge ServiceStatusCell).
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex">
            <LeadStatusBadge value={value} />
          </span>
        </TooltipTrigger>
        <TooltipContent>{t("lead_status_edit.role_required")}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="focus-visible:ring-ring hover:bg-muted inline-flex rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none"
          aria-label={t("lead_status_edit.aria", { reference })}
        >
          <LeadStatusBadge value={value} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-48 p-2">
        <p className="text-muted-foreground px-2 pt-1 pb-2 text-xs font-medium">
          {t("lead_status_edit.title")}
        </p>
        <ul className="space-y-0.5">
          {LEAD_STATUSES.map((option) => (
            <li key={option}>
              <button
                type="button"
                onClick={() => {
                  if (option !== value) {
                    setLeadStatus.mutate(option, {
                      onError: () => toast.error(t("lead_status_edit.error")),
                    });
                  }
                  setOpen(false);
                }}
                className={cn(
                  "hover:bg-muted flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                  option === value && "bg-muted font-medium",
                )}
              >
                <span
                  className="size-2 rounded-full"
                  style={{ backgroundColor: leadStatusColorVar[option] }}
                  aria-hidden
                />
                <span>{leadStatusLabel(option)}</span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
