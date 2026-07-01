import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useChangeOverRules,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertyRatePlans,
  usePropertyServices,
  usePropertySettings,
} from "@/features/properties/hooks";
import type { PropertyDetail } from "@/features/properties/schemas";
import { useRatePlanDetailsFanOut } from "./hooks";
import { toLanes } from "./toLanes";
import { useYearWindow } from "./yearWindow";
import { WorkbenchTimeline } from "./components/WorkbenchTimeline";
import { MatrixEditor } from "./components/MatrixEditor";
import { InspectorPanel } from "./components/InspectorPanel";
import { PriceProbePanel } from "./components/PriceProbePanel";

interface WorkbenchContext {
  property: PropertyDetail;
}

/**
 * The Rate & Service Workbench: a unified, whole-year view of a property's
 * commercial configuration. Preview tab that sits alongside the existing
 * Pricing tab. Phase 1 is the read-only timeline overview; matrix editing,
 * inline inspectors and the live price probe land in later phases.
 */
export function RateWorkbenchPage() {
  const { t } = useTranslation("properties");
  const { property } = useOutletContext<WorkbenchContext>();
  const { year, windowStart, dayCount, from, to, goPrev, goNext } = useYearWindow();
  const canWrite = useHasReservationsRole();

  const seasons = usePropertyRatePlans(property.id);
  const services = usePropertyServices(property.id);
  const extras = usePropertyExtras(property.id);
  const discounts = usePropertyDiscounts(property.id);
  const changeover = useChangeOverRules(property.id);
  const settings = usePropertySettings(property.id);

  const seasonList = seasons.data?.results ?? [];
  const fanOut = useRatePlanDetailsFanOut(seasonList.map((s) => s.id));

  // Which season's rate matrix is open (below the timeline). Defaults to the
  // first season that has periods once details load.
  const [matrixRatePlanId, setMatrixRatePlanId] = useState<number | null>(null);

  const isLoading =
    seasons.isLoading ||
    services.isLoading ||
    extras.isLoading ||
    discounts.isLoading ||
    changeover.isLoading ||
    fanOut.isLoading;

  const isError =
    seasons.isError ||
    services.isError ||
    extras.isError ||
    discounts.isError ||
    changeover.isError ||
    fanOut.isError;

  const header = (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-foreground flex items-center gap-2 font-serif text-2xl font-semibold">
          {t("rate_workbench.title")}
          <Badge variant="secondary">{t("rate_workbench.preview_badge")}</Badge>
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("rate_workbench.subtitle")}</p>
      </div>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          onClick={goPrev}
          aria-label={t("rate_workbench.year.prev")}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="w-14 text-center text-sm font-medium tabular-nums">{year}</span>
        <Button
          variant="outline"
          size="icon"
          onClick={goNext}
          aria-label={t("rate_workbench.year.next")}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );

  let body: React.ReactNode;
  if (isLoading) {
    body = <Skeleton className="h-72 w-full" />;
  } else if (isError) {
    body = (
      <ErrorState
        title={t("rate_workbench.error.title")}
        description={t("rate_workbench.error.body")}
        onRetry={() => {
          void seasons.refetch();
          void services.refetch();
          void extras.refetch();
          void discounts.refetch();
          void changeover.refetch();
          fanOut.refetch();
        }}
      />
    );
  } else {
    const serviceList = services.data?.results ?? [];
    const extraList = extras.data?.results ?? [];
    const discountList = discounts.data?.results ?? [];
    const changeoverList = changeover.data?.results ?? [];
    const lanes = toLanes({
      windowStart,
      dayCount,
      windowFrom: from,
      windowTo: to,
      seasons: seasonList,
      ratePlanDetails: fanOut.details,
      services: serviceList,
      extras: extraList,
      discounts: discountList,
      changeover: changeoverList,
    });
    // A property with no commercial config at all vs. one whose config all falls
    // in other years are different states: the latter must not read as "nothing
    // configured" (it would invite re-entering data that already exists).
    const hasAnyConfig =
      seasonList.length > 0 ||
      serviceList.length > 0 ||
      extraList.length > 0 ||
      discountList.length > 0 ||
      changeoverList.length > 0;
    const isEmptyForYear = lanes.every((lane) => lane.bands.length === 0);
    if (!hasAnyConfig) {
      body = (
        <EmptyState
          title={t("rate_workbench.empty.title")}
          description={t("rate_workbench.empty.body")}
        />
      );
    } else if (isEmptyForYear) {
      body = (
        <EmptyState
          title={t("rate_workbench.empty_year.title", { year })}
          description={t("rate_workbench.empty_year.body")}
        />
      );
    } else {
      body = <WorkbenchTimeline lanes={lanes} windowStart={windowStart} dayCount={dayCount} />;
    }
  }

  // The rate matrix is season/period-structural, not year-scoped, so it renders
  // below the timeline whenever any loaded season has periods — independent of
  // the year in view.
  const seasonsWithPeriods = fanOut.details.filter((d) => (d.periods?.length ?? 0) > 0);
  const activeMatrixRatePlanId =
    matrixRatePlanId != null && seasonsWithPeriods.some((s) => s.id === matrixRatePlanId)
      ? matrixRatePlanId
      : (seasonsWithPeriods[0]?.id ?? null);

  const matrixSection =
    !isLoading && !isError && activeMatrixRatePlanId != null ? (
      <section className="border-border space-y-3 border-t pt-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-foreground text-lg font-semibold">
            {t("rate_workbench.matrix.title")}
          </h2>
          {seasonsWithPeriods.length > 1 ? (
            <Select
              value={String(activeMatrixRatePlanId)}
              onValueChange={(v) => setMatrixRatePlanId(Number(v))}
            >
              <SelectTrigger
                className="w-[220px]"
                aria-label={t("rate_workbench.matrix.season_picker")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {seasonsWithPeriods.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
        </div>
        <MatrixEditor
          key={activeMatrixRatePlanId}
          ratePlanId={activeMatrixRatePlanId}
          seasons={seasonsWithPeriods}
          canWrite={canWrite}
          commission={settings.data?.commission ?? null}
          tax={settings.data?.tax ?? null}
        />
      </section>
    ) : null;

  // The property's pricing currency: seasons carry the authoritative currency
  // (both the `currency` FK id and its `currency_code`, set together), but the
  // property settings row often leaves the FK null (only the group resolves one).
  // Read both from a single season so the inspector's amount adornments (code)
  // and the extra dialog's currency default (id) stay consistent; fall back to
  // the settings code for display.
  const currencySeason = seasonList.find((s) => s.currency != null || s.currency_code);
  const currencyCode = currencySeason?.currency_code ?? settings.data?.currency_code ?? null;
  const defaultCurrencyId = currencySeason?.currency ?? null;

  const inspectorSection =
    !isLoading && !isError ? (
      <InspectorPanel
        propertyId={property.id}
        canWrite={canWrite}
        currencyCode={currencyCode}
        defaultCurrencyId={defaultCurrencyId}
      />
    ) : null;

  // periodId → "Season · Period", so the probe can name the winning period.
  // Memoised so unrelated re-renders (year paging, matrix/inspector edits) don't
  // rebuild the map or hand the probe a fresh object reference each time.
  const periodLabels = useMemo(() => {
    const labels: Record<number, string> = {};
    for (const detail of fanOut.details) {
      for (const period of detail.periods ?? []) {
        const label =
          period.name || `${formatDate(period.date_from)} – ${formatDate(period.date_to)}`;
        labels[period.id] = `${detail.name} · ${label}`;
      }
    }
    return labels;
  }, [fanOut.details]);
  const probeSection =
    !isLoading && !isError ? (
      <PriceProbePanel
        propertyId={property.id}
        extras={extras.data?.results ?? []}
        periodLabels={periodLabels}
      />
    ) : null;

  return (
    <div className="space-y-6 p-6">
      {header}
      {body}
      {matrixSection}
      {inspectorSection}
      {probeSection}
    </div>
  );
}
