import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { addDaysIso } from "@/lib/format/date";
import { periodLabel } from "@/features/properties/periodLabel";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useChangeOverRules,
  useDeleteRatePlan,
  useDuplicateRatePlan,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertyRatePlans,
  usePropertyServices,
  usePropertySettings,
} from "@/features/properties/hooks";
import { CarryForwardDialog } from "./components/CarryForwardDialog";
import { PricingModeToggle } from "./components/PricingModeToggle";
import { RatePeriodFormDialog } from "@/features/properties/components/RatePeriodFormDialog";
import { RatePlanFormDialog } from "@/features/properties/components/RatePlanFormDialog";
import type { PropertyDetail, RatePlan } from "@/features/properties/schemas";
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
 * The "Rates" tab (internal name: rate workbench): a unified, whole-year view of
 * a property's commercial configuration — the whole-year timeline overview,
 * the season/period rate matrix editor, inline inclusion/extra/discount
 * inspectors, and a live guest-side price probe. Since GAP-060 it is the single
 * rate-editing surface, superseding the retired Pricing tab.
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
  // Four openers share it — header button / matrix empty state (day after the
  // latest period), coverage-gap clicks (the gap's own inclusive range), and
  // the per-period timeline "+" (free range after the period, which also
  // names the owning plan; without a planId the matrix's plan is the target).
  const [periodPrefill, setPeriodPrefill] = useState<{
    planId?: number;
    date_from?: string;
    date_to?: string;
  } | null>(null);

  // Rate-plan (season) lifecycle, ported from the retired Pricing tab. Create
  // is offered from the always-rendered header (and the zero-config empty
  // state) so a plan-less property is bootstrappable; edit/duplicate/delete act
  // on the currently-selected matrix season via its actions menu.
  const deleteSeasonMutation = useDeleteRatePlan(property.id);
  const duplicateSeasonMutation = useDuplicateRatePlan(property.id);
  const [addSeasonOpen, setAddSeasonOpen] = useState(false);
  const [editingSeason, setEditingSeason] = useState<RatePlan | null>(null);
  const [duplicatingSeason, setDuplicatingSeason] = useState<RatePlan | null>(null);
  const [deletingSeason, setDeletingSeason] = useState<RatePlan | null>(null);
  // Carry-forward (GAP-069): open state for the projected-year promotion dialog.
  const [carryForwardOpen, setCarryForwardOpen] = useState(false);

  const handleDeleteSeason = async () => {
    if (!deletingSeason) return;
    try {
      await deleteSeasonMutation.mutateAsync({ ratePlanId: deletingSeason.id });
      toast.success(t("pricing.seasons.toasts.deleted"));
      if (matrixRatePlanId === deletingSeason.id) setMatrixRatePlanId(null);
      setDeletingSeason(null);
    } catch {
      toast.error(t("pricing.seasons.toasts.delete_failed"));
    }
  };

  const handleDuplicateSeason = async () => {
    if (!duplicatingSeason) return;
    try {
      await duplicateSeasonMutation.mutateAsync({ ratePlanId: duplicatingSeason.id });
      toast.success(t("pricing.seasons.toasts.duplicated"));
      setDuplicatingSeason(null);
    } catch {
      toast.error(t("pricing.seasons.toasts.duplicate_failed"));
    }
  };

  // Writer-gated add affordance; disabled-in-tooltip, never hidden
  // (frontend/CLAUDE.md role gating). Shared by the header and the empty state.
  const addSeasonButton = canWrite ? (
    <Button size="sm" onClick={() => setAddSeasonOpen(true)}>
      {t("pricing.seasons.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("pricing.seasons.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("pricing.seasons.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  const isLoading =
    seasons.isLoading ||
    services.isLoading ||
    extras.isLoading ||
    discounts.isLoading ||
    changeover.isLoading ||
    // Only the FIRST fan-out load blanks the page. Once any season detail has
    // resolved, a still-loading member (e.g. the plan just created/duplicated
    // in-page, which grows the fan-out) must not collapse the whole workbench
    // to a skeleton — the existing seasons stay rendered while it loads.
    (fanOut.isLoading && fanOut.details.length === 0);

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
        <h1 className="text-foreground font-serif text-2xl font-semibold">
          {t("rate_workbench.title")}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("rate_workbench.subtitle")}</p>
      </div>
      <div className="flex items-center gap-2">
        {addSeasonButton}
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
      : // Prefer a plan with periods in the year on screen. The timeline is now
        // plan-scoped, so a multi-currency property whose plans live in different
        // years must not default to one with nothing this year — that would read
        // as "nothing scheduled" and hide the others. Falls back to any plan with
        // periods, then the first plan.
        (allSeasonDetails.find((d) =>
          (d.periods ?? []).some((p) => p.date_from < to && p.date_to >= from),
        )?.id ??
        allSeasonDetails.find((d) => (d.periods?.length ?? 0) > 0)?.id ??
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

  // GAP-026 (ported from the retired RatePlanDetailPanel): softly flag — never
  // block — an active season whose currency diverges from the property's
  // effective currency.
  const propertyCurrencyCode = settings.data?.currency_code ?? null;
  const activeSeasonCurrencyCode = activeSeasonDetail?.currency_code ?? null;
  const currencyMismatch =
    !!propertyCurrencyCode &&
    !!activeSeasonCurrencyCode &&
    propertyCurrencyCode.toUpperCase() !== activeSeasonCurrencyCode.toUpperCase();

  // Carry-forward (GAP-069): in the empty-year (projected) state, a writer can
  // promote an earlier year's rates into the year on screen. Offered only when
  // the active plan has a resolvable currency CODE (the endpoint carries by
  // Currency.code) and the target isn't in the past (the backend's window guard
  // rejects `target_year < this_year`).
  const carryForwardEligible = !!activeSeasonCurrencyCode && year >= new Date().getFullYear();
  const carryForwardButton = canWrite ? (
    <Button size="sm" onClick={() => setCarryForwardOpen(true)}>
      {t("rate_workbench.carry_forward.button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("rate_workbench.carry_forward.button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("rate_workbench.carry_forward.button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );
  // If the active plan's currency vanishes while the dialog is open (e.g. a
  // background refetch empties the plan list), close it — otherwise the stale
  // `carryForwardOpen` flag could re-mount the dialog once a plan reappears.
  useEffect(() => {
    if (carryForwardOpen && !activeSeasonCurrencyCode) setCarryForwardOpen(false);
  }, [carryForwardOpen, activeSeasonCurrencyCode]);

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
      // The top rate-plan picker scopes the whole view: the rates lane (and the
      // derived coverage lane below) reflect only the selected plan. For the
      // common single-plan villa this is the one plan, unchanged; for a
      // multi-currency property it keeps each currency's periods in their own
      // coherent view rather than stacking mixed currencies in one lane.
      ratePlanDetails: activeSeasonDetail ? [activeSeasonDetail] : [],
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
          action={addSeasonButton}
        />
      );
    } else if (isEmptyForYear) {
      body = (
        <EmptyState
          title={t("rate_workbench.empty_year.title", { year })}
          description={t("rate_workbench.empty_year.body")}
          action={carryForwardEligible ? carryForwardButton : undefined}
        />
      );
    } else {
      body = (
        <WorkbenchTimeline
          lanes={lanes}
          windowStart={windowStart}
          dayCount={dayCount}
          onCreatePeriod={canWrite ? (prefill) => setPeriodPrefill(prefill) : undefined}
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
            {activeSeasonDetail ? (
              <PricingModeToggle
                propertyId={property.id}
                ratePlan={activeSeasonDetail}
                canWrite={canWrite}
              />
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
        {currencyMismatch ? (
          <p
            role="status"
            className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-xs"
          >
            {t("pricing.season_detail.currency_mismatch", {
              season: activeSeasonCurrencyCode,
              property: propertyCurrencyCode,
            })}
          </p>
        ) : null}
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
            key={periodPrefill.planId ?? activeMatrixRatePlanId}
            ratePlanId={periodPrefill.planId ?? activeMatrixRatePlanId}
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
        labels[period.id] = `${detail.name} · ${periodLabel(period)}`;
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

  // The rate-plan (currency) picker sits at the very top because it scopes the
  // whole view — timeline periods, coverage, and the matrix all follow it.
  // Rendered only when several plans exist (one per currency; most villas have
  // exactly one, so no picker). The ··· menu edits/duplicates/deletes the
  // selected plan; writer-only. Suppressed entirely when neither is applicable.
  const planBar =
    !isLoading && !isError && activeSeasonDetail && (allSeasonDetails.length > 1 || canWrite) ? (
      <div className="flex items-center gap-2">
        {allSeasonDetails.length > 1 ? (
          <Select
            value={String(activeMatrixRatePlanId)}
            onValueChange={(v) => setMatrixRatePlanId(Number(v))}
          >
            <SelectTrigger
              className="w-[240px]"
              aria-label={t("rate_workbench.matrix.rate_plan_picker")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {allSeasonDetails.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.currency_code ? `${s.name} · ${s.currency_code}` : s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          // Single plan: no picker, so name the plan the ··· menu acts on.
          <span className="text-foreground text-sm font-medium">
            {activeSeasonDetail.currency_code
              ? `${activeSeasonDetail.name} · ${activeSeasonDetail.currency_code}`
              : activeSeasonDetail.name}
          </span>
        )}
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2"
                aria-label={t("pricing.seasons.row.menu_label")}
              >
                ···
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setEditingSeason(activeSeasonDetail)}>
                {t("pricing.seasons.row.edit")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setDuplicatingSeason(activeSeasonDetail)}>
                {t("pricing.seasons.row.duplicate")}
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onClick={() => setDeletingSeason(activeSeasonDetail)}
              >
                {t("pricing.seasons.row.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    ) : null;

  return (
    <div className="space-y-6 p-6">
      {header}
      {planBar}
      {body}
      {matrixSection}
      {inspectorSection}
      {probeSection}

      {addSeasonOpen ? (
        <RatePlanFormDialog
          propertyId={property.id}
          open
          onOpenChange={setAddSeasonOpen}
          mode="create"
        />
      ) : null}
      {carryForwardOpen && activeSeasonCurrencyCode ? (
        <CarryForwardDialog
          propertyId={property.id}
          currencyCode={activeSeasonCurrencyCode}
          targetYear={year}
          open
          onOpenChange={setCarryForwardOpen}
          onCarried={(plan) => setMatrixRatePlanId(plan.id)}
        />
      ) : null}
      {editingSeason ? (
        <RatePlanFormDialog
          propertyId={property.id}
          open
          onOpenChange={(o) => !o && setEditingSeason(null)}
          mode="edit"
          season={editingSeason}
        />
      ) : null}
      {deletingSeason ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingSeason(null)}
          onConfirm={handleDeleteSeason}
          title={t("pricing.seasons.delete_confirm.title")}
          description={t("pricing.seasons.delete_confirm.description")}
          confirmLabel={t("pricing.seasons.delete_confirm.confirm")}
          destructive
          busy={deleteSeasonMutation.isPending}
        />
      ) : null}
      {duplicatingSeason ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDuplicatingSeason(null)}
          onConfirm={handleDuplicateSeason}
          title={t("pricing.seasons.duplicate_confirm.title")}
          description={t("pricing.seasons.duplicate_confirm.description")}
          confirmLabel={t("pricing.seasons.duplicate_confirm.confirm")}
          busy={duplicateSeasonMutation.isPending}
        />
      ) : null}
    </div>
  );
}
