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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { addDaysIso, formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { asPriceBasis, type PriceBasis } from "@/lib/pricing/netGross";
import {
  useChangeOverRules,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertyRatePlans,
  usePropertyServices,
  usePropertySettings,
} from "@/features/properties/hooks";
import { RatePeriodFormDialog } from "@/features/properties/components/RatePeriodFormDialog";
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

  const seasonList = useMemo(() => seasons.data?.results ?? [], [seasons.data]);
  const fanOut = useRatePlanDetailsFanOut(seasonList.map((s) => s.id));

  // Which season's rate matrix is open (below the timeline). Defaults to the
  // first season that has periods once details load.
  const [matrixRatePlanId, setMatrixRatePlanId] = useState<number | null>(null);
  // Period-create dialog: null = closed; an (empty-allowed) prefill = open.
  // Three openers share it — header button / matrix empty state (day after the
  // latest period) and coverage-gap clicks (the gap's own inclusive range).
  const [periodPrefill, setPeriodPrefill] = useState<{
    date_from?: string;
    date_to?: string;
  } | null>(null);

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

  // The rate matrix is season/period-structural, not year-scoped, so it renders
  // below the timeline whenever any season has loaded — independent of the year
  // in view. ALL plans are selectable: a zero-period plan is exactly the one
  // that needs the "Add period" flow, so it must not be filtered out of reach.
  const allSeasonDetails = fanOut.details;
  const activeMatrixRatePlanId =
    matrixRatePlanId != null && allSeasonDetails.some((s) => s.id === matrixRatePlanId)
      ? matrixRatePlanId
      : (allSeasonDetails.find((d) => (d.periods?.length ?? 0) > 0)?.id ??
        allSeasonDetails[0]?.id ??
        null);

  // "Add period" prefill: the day after the selected plan's latest period
  // (inactive ones included — the DB EXCLUDE rejects overlaps regardless of
  // is_active), so consecutive creates walk forward gap-free.
  const activeSeasonDetail = allSeasonDetails.find((s) => s.id === activeMatrixRatePlanId) ?? null;
  const latestPeriodEnd = (activeSeasonDetail?.periods ?? []).reduce<string | null>(
    (max, p) => (max == null || p.date_to > max ? p.date_to : max),
    null,
  );
  const periodInitialValues = latestPeriodEnd
    ? { date_from: addDaysIso(latestPeriodEnd, 1) }
    : undefined;

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
      coveragePlanId: activeMatrixRatePlanId,
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
    // The coverage lane is derived (it has bands precisely when nothing is
    // priced), so it must not count as "something scheduled this year".
    const isEmptyForYear = lanes
      .filter((lane) => lane.key !== "coverage")
      .every((lane) => lane.bands.length === 0);
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
      body = (
        <WorkbenchTimeline
          lanes={lanes}
          windowStart={windowStart}
          dayCount={dayCount}
          onGapClick={
            canWrite
              ? (gap) => setPeriodPrefill({ date_from: gap.from, date_to: gap.to })
              : undefined
          }
        />
      );
    }
  }

  const matrixSection =
    !isLoading && !isError && activeMatrixRatePlanId != null ? (
      <section className="border-border space-y-3 border-t pt-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-foreground text-lg font-semibold">
            {t("rate_workbench.matrix.title")}
          </h2>
          <div className="flex items-center gap-2">
            {allSeasonDetails.length > 1 ? (
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
                  {allSeasonDetails.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            {/* Only when the plan has periods — a zero-period plan's create
                affordance lives in the matrix empty state instead. Disabled,
                never hidden, for non-writers (frontend/CLAUDE.md role gating). */}
            {(activeSeasonDetail?.periods?.length ?? 0) > 0 ? (
              canWrite ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPeriodPrefill(periodInitialValues ?? {})}
                >
                  {t("rate_workbench.matrix.add_period")}
                </Button>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span>
                      <Button variant="outline" size="sm" disabled>
                        {t("rate_workbench.matrix.add_period")}
                      </Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    {t("rate_workbench.matrix.add_period_disabled_tooltip")}
                  </TooltipContent>
                </Tooltip>
              )
            ) : null}
          </div>
        </div>
        <MatrixEditor
          key={activeMatrixRatePlanId}
          ratePlanId={activeMatrixRatePlanId}
          seasons={allSeasonDetails}
          canWrite={canWrite}
          commission={settings.data?.commission ?? null}
          tax={settings.data?.tax ?? null}
          onAddPeriod={() => setPeriodPrefill(periodInitialValues ?? {})}
        />
        {periodPrefill != null ? (
          <RatePeriodFormDialog
            key={activeMatrixRatePlanId}
            ratePlanId={activeMatrixRatePlanId}
            open
            onOpenChange={(o) => {
              if (!o) setPeriodPrefill(null);
            }}
            mode="create"
            initialValues={periodPrefill}
            changeoverDay={settings.data?.changeover_day ?? null}
            minNightsRental={settings.data?.min_nights_rental ?? null}
          />
        ) : null}
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
  // Every currency an ACTIVE rate plan prices in — the extra dialog warns when
  // an extra's currency is outside this set (the engine only quotes in active
  // plans' currencies and hard-filters extras by quote currency). If any active
  // plan inherits its currency (null FK, group-resolved code), the universe is
  // unknowable by id — pass undefined so the hint stays silent rather than
  // firing falsely.
  const planCurrencyIds = useMemo(() => {
    const active = seasonList.filter((s) => s.is_active !== false);
    if (active.length === 0 || active.some((s) => s.currency == null)) return undefined;
    return [...new Set(active.map((s) => s.currency as number))];
  }, [seasonList]);

  const inspectorSection =
    !isLoading && !isError ? (
      <InspectorPanel
        propertyId={property.id}
        canWrite={canWrite}
        currencyCode={currencyCode}
        defaultCurrencyId={defaultCurrencyId}
        planCurrencyIds={planCurrencyIds}
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
  // planId → price basis, so the probe can reconcile the guest total against the
  // winning plan's basis (GROSS vs NET — see QuoteResultCard). The list season
  // carries both `plan_id`-equivalent `id` and `price_basis`.
  const basisByPlan = useMemo(() => {
    const map: Record<number, PriceBasis> = {};
    for (const season of seasons.data?.results ?? []) {
      if (season.price_basis) map[season.id] = season.price_basis;
    }
    return map;
  }, [seasons.data]);
  const probeSection =
    !isLoading && !isError ? (
      <PriceProbePanel
        propertyId={property.id}
        extras={extras.data?.results ?? []}
        periodLabels={periodLabels}
        basisByPlan={basisByPlan}
        defaultBasis={asPriceBasis(settings.data?.prices_entered_as_effective)}
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
