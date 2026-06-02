import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ServiceDot, SERVICE_STATUSES, type ServiceStatus } from "@/components/data/ServiceDot";
import type { ServiceKey } from "@/styles/tokens";
import { cn } from "@/lib/cn";
import { serviceLabel, serviceStatusLabel } from "../schemas";

interface ServiceStatusCellProps {
  service: ServiceKey;
  status: ServiceStatus;
  reference: string;
  canWrite: boolean;
  onSelect: (status: ServiceStatus) => void;
}

/**
 * One matrix cell: a service dot that opens a status picker. Without the
 * reservations role the dot renders read-only inside a tooltip (affordances
 * disable, never disappear).
 */
export function ServiceStatusCell({
  service,
  status,
  reference,
  canWrite,
  onSelect,
}: ServiceStatusCellProps) {
  const { t } = useTranslation("concierge");
  const [open, setOpen] = useState(false);
  const dotLabel = `${serviceLabel(service)} — ${serviceStatusLabel(status)}`;

  if (!canWrite) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex">
            <ServiceDot service={service} status={status} label={dotLabel} />
          </span>
        </TooltipTrigger>
        <TooltipContent>{t("role_required_tooltip")}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="focus-visible:ring-ring hover:bg-muted inline-flex rounded-full p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
          aria-label={t("popover.aria_label", { service: serviceLabel(service), reference })}
        >
          <ServiceDot service={service} status={status} label={dotLabel} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-2">
        <p className="text-muted-foreground px-2 pt-1 pb-2 text-xs font-medium">
          {t("popover.title", { service: serviceLabel(service) })}
        </p>
        <ul className="space-y-0.5">
          {SERVICE_STATUSES.map((option) => (
            <li key={option}>
              <button
                type="button"
                onClick={() => {
                  onSelect(option);
                  setOpen(false);
                }}
                className={cn(
                  "hover:bg-muted flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                  option === status && "bg-muted font-medium",
                )}
              >
                <ServiceDot service={service} status={option} label={serviceStatusLabel(option)} />
                <span>{serviceStatusLabel(option)}</span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
