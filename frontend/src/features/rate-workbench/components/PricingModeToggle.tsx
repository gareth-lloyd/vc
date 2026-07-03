import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUpdateRatePlan } from "@/features/properties/hooks";
import type { PropertyId } from "@/lib/query/keys";
import type { RatePlanDetail } from "@/features/properties/schemas";

interface PricingModeToggleProps {
  propertyId: PropertyId;
  ratePlan: RatePlanDetail;
  canWrite: boolean;
}

/**
 * Flat ↔ by-occupancy switch for the active rate plan. Flat plans price one
 * rate per period (party size ignored); occupancy plans carry per-party bands.
 *
 * Switching to flat is only offered once every period holds a single band —
 * collapsing a multi-band period has no single price to keep, so we make the
 * operator reduce it first (mirrors the backend guard, so the disabled reason
 * is shown here rather than surfaced as a 400). Switching to occupancy is
 * always available; the operator then splits the base band.
 */
export function PricingModeToggle({ propertyId, ratePlan, canWrite }: PricingModeToggleProps) {
  const { t } = useTranslation("properties");
  const update = useUpdateRatePlan(propertyId);
  const byOccupancy = ratePlan.prices_by_occupancy ?? false;
  const canGoFlat = !(ratePlan.periods ?? []).some((p) => (p.bands?.length ?? 0) > 1);

  const setMode = (next: boolean) => {
    if (next === byOccupancy) return;
    update.mutate(
      { ratePlanId: ratePlan.id, input: { prices_by_occupancy: next } },
      { onError: () => toast.error(t("rate_workbench.pricing_mode.save_failed")) },
    );
  };

  // Switching to flat is blocked (not just role-gated) while a period is
  // multi-band — surface the reason on the disabled control.
  const flatBlocked = byOccupancy && !canGoFlat;
  const flatDisabled = !canWrite || update.isPending || flatBlocked;

  const flatButton = (
    <Button
      type="button"
      size="sm"
      variant={byOccupancy ? "ghost" : "secondary"}
      aria-pressed={!byOccupancy}
      disabled={flatDisabled}
      onClick={() => setMode(false)}
    >
      {t("rate_workbench.pricing_mode.flat")}
    </Button>
  );

  return (
    <div
      role="group"
      aria-label={t("rate_workbench.pricing_mode.label")}
      className="border-border inline-flex items-center gap-1 rounded-md border p-0.5"
    >
      {flatBlocked ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>{flatButton}</span>
          </TooltipTrigger>
          <TooltipContent>{t("rate_workbench.pricing_mode.flat_blocked")}</TooltipContent>
        </Tooltip>
      ) : (
        flatButton
      )}
      <Button
        type="button"
        size="sm"
        variant={byOccupancy ? "secondary" : "ghost"}
        aria-pressed={byOccupancy}
        disabled={!canWrite || update.isPending}
        onClick={() => setMode(true)}
      >
        {t("rate_workbench.pricing_mode.occupancy")}
      </Button>
    </div>
  );
}
