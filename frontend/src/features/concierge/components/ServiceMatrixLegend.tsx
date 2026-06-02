import { useTranslation } from "react-i18next";
import { ServiceDot, SERVICE_STATUSES } from "@/components/data/ServiceDot";
import { serviceStatusLabel } from "../schemas";

/**
 * Footer legend explaining the six service-status fills. A single representative
 * ring colour (`other`) is used for every swatch so the eye reads the *fill*
 * progression, not the service hue.
 */
export function ServiceMatrixLegend() {
  const { t } = useTranslation("concierge");
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {t("legend.title")}
      </span>
      {SERVICE_STATUSES.map((status) => (
        <span key={status} className="flex items-center gap-1.5 text-sm">
          <ServiceDot service="other" status={status} label={serviceStatusLabel(status)} />
          <span className="text-muted-foreground">{serviceStatusLabel(status)}</span>
        </span>
      ))}
    </div>
  );
}
