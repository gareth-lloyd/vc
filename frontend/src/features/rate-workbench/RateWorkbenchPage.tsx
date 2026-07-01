import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import {
  useChangeOverRules,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertySeasons,
  usePropertyServices,
} from "@/features/properties/hooks";
import type { PropertyDetail } from "@/features/properties/schemas";
import { useSeasonDetailsFanOut } from "./hooks";
import { toLanes } from "./toLanes";
import { useYearWindow } from "./yearWindow";
import { WorkbenchTimeline } from "./components/WorkbenchTimeline";

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

  const seasons = usePropertySeasons(property.id);
  const services = usePropertyServices(property.id);
  const extras = usePropertyExtras(property.id);
  const discounts = usePropertyDiscounts(property.id);
  const changeover = useChangeOverRules(property.id);

  const seasonList = seasons.data?.results ?? [];
  const fanOut = useSeasonDetailsFanOut(seasonList.map((s) => s.id));

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
      seasonDetails: fanOut.details,
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

  return (
    <div className="space-y-6 p-6">
      {header}
      {body}
    </div>
  );
}
