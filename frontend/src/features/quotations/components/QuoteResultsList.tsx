import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { propertyDetailsPath } from "@/lib/routes";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { QuoteResultLine } from "./QuoteResultLine";
import {
  type HiddenCapacityProperty,
  type QuoteOption,
  type StayAdd,
  stagedLineProperty,
} from "../schemas";

interface Props {
  options: QuoteOption[] | undefined;
  isLoading: boolean;
  // Staged line_ids (GAP-043). Full result cards mark individual weeks off
  // these; the compact manual/unavailable rows decode them per property (one
  // row per villa, staged when ANY of its weeks is).
  stagedKeys: Set<string>;
  // The dates the current results were searched with — full cards need them
  // to map week cells onto staged-line identities. Null only before the first
  // search, when there are no results to render.
  criteriaDates: { date_from: string; date_to: string } | null;
  // GAP-043: one add-unit per checked week (each with its GAP-044 bands);
  // absent for the compact manual-quotable rows (criteria-dates line).
  onAdd: (option: QuoteOption, adds?: StayAdd[]) => void;
  // Party the search ran with — block reprices keep the same party.
  adults: number;
  children: number;
  // Identity of the current search (dates + flex). Rows key on it so a fresh
  // search remounts picker/reprice state while Load-more appends preserve it.
  searchKey: string;
  hiddenForCapacity?: HiddenCapacityProperty[];
  // There are more candidate pages to price (DRF `next`).
  hasMore: boolean;
  // A Load-more page is being priced — disables the button, leaves results up.
  isLoadingMore: boolean;
  // Total candidates matching the criteria across all pages (DRF `count`).
  totalMatched: number;
  onLoadMore: () => void;
}

function CapacityHint({ properties }: { properties: HiddenCapacityProperty[] }) {
  const { t } = useTranslation("quotations");
  if (properties.length === 0) return null;
  return (
    <div
      className="border-border bg-muted/40 space-y-2 rounded-md border border-dashed p-3"
      role="status"
    >
      <p className="text-muted-foreground text-xs">{t("builder.results.capacity_hint.intro")}</p>
      <ul className="space-y-1">
        {properties.map((p) => (
          <li key={p.id} className="text-sm">
            <Link to={propertyDetailsPath(p.slug ?? p.id)} className="font-medium underline">
              {p.name}
            </Link>{" "}
            <span className="text-muted-foreground">
              {t("builder.results.capacity_hint.suffix")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Distinct villas can share a guest-facing display name (the card title), so
// the meta line carries the internal name (when it differs) and the capacity
// headline to tell same-named results apart.
function OptionMeta({ option }: { option: QuoteOption }) {
  const { t } = useTranslation("quotations");
  const parts: string[] = [];
  if (option.internal_name && option.internal_name !== option.property_name) {
    parts.push(option.internal_name);
  }
  if (option.bedrooms != null) {
    parts.push(t("builder.results.bedrooms", { count: option.bedrooms }));
  }
  if (option.sleeps != null) {
    parts.push(t("builder.results.sleeps", { count: option.sleeps }));
  }
  if (parts.length === 0) return null;
  return <p className="text-muted-foreground text-xs">{parts.join(" · ")}</p>;
}

export function QuoteResultsList({
  options,
  isLoading,
  stagedKeys,
  criteriaDates,
  onAdd,
  adults,
  children,
  searchKey,
  hiddenForCapacity = [],
  hasMore,
  isLoadingMore,
  totalMatched,
  onLoadMore,
}: Props) {
  const { t } = useTranslation("quotations");

  // Decode the staged keys once per render: one card per villa, "staged" when
  // ANY of its week-lines is.
  const stagedProperties = new Set(Array.from(stagedKeys, stagedLineProperty));
  const isPropertyStaged = (propertyId: number): boolean => stagedProperties.has(propertyId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (options == null) {
    return (
      <EmptyState
        title={t("builder.results.idle.title")}
        description={t("builder.results.idle.description")}
      />
    );
  }

  if (options.length === 0) {
    return (
      <div className="space-y-3">
        <EmptyState
          title={t("builder.results.empty.title")}
          description={t("builder.results.empty.description")}
        />
        <CapacityHint properties={hiddenForCapacity} />
      </div>
    );
  }

  // GAP-044 B2: a result can be !available for a PRICING reason (e.g.
  // party_out_of_range) yet still carry occupancy bands — those render the full
  // card so the bands show. A booked week (`dates_unavailable`) is not
  // date-available, so its bands are suppressed and it stays in the compact
  // unavailable list like any other booked villa (plan decision 3: bands are
  // gated on the week being date-available, not booked).
  const showsBands = (o: QuoteOption) =>
    (o.occupancy_bands?.length ?? 0) > 0 && o.error_code !== "dates_unavailable";
  const available = options.filter((o) => o.available);
  // Full result cards: truly available results plus date-available banded ones.
  const fullCard = options.filter((o) => o.available || showsBands(o));
  // Q-013: villas the engine can't price (missing rate rules or POA) stay
  // quotable with an operator-typed price, per legacy NO RATE behaviour —
  // flagged in the main list, never hidden.
  const manualQuotable = options.filter(
    (o) => !o.available && !showsBands(o) && o.error_code === "no_rate_available",
  );
  const unavailable = options.filter(
    (o) => !o.available && !showsBands(o) && o.error_code !== "no_rate_available",
  );

  return (
    <div className="space-y-3">
      <CapacityHint properties={hiddenForCapacity} />
      {fullCard.map((option) => (
        <QuoteResultLine
          key={`${option.property_id}:${searchKey}`}
          option={option}
          stagedKeys={stagedKeys}
          criteriaDates={criteriaDates ?? { date_from: "", date_to: "" }}
          adults={adults}
          children={children}
          onAdd={onAdd}
        />
      ))}

      {manualQuotable.map((option) => (
        <article
          key={option.property_id}
          className="border-border flex items-center justify-between gap-3 rounded-md border p-3"
          aria-label={t("builder.results.incomplete_pricing_aria", {
            name: option.property_name,
          })}
        >
          <div className="flex items-center gap-3">
            <PropertyThumbnail
              src={option.hero_image_url}
              fallbackText={option.property_name}
              alt={t("builder.results.thumbnail_alt", { name: option.property_name })}
            />
            <div>
              <h4 className="text-foreground text-sm font-semibold">{option.property_name}</h4>
              <OptionMeta option={option} />
              <Tooltip>
                <TooltipTrigger asChild>
                  {/* tabIndex makes the badge keyboard-focusable so the tooltip
                      (the only place POA is distinguished from a rate-card gap)
                      opens on focus, not just hover. */}
                  <p tabIndex={0} className="text-warning text-xs font-medium">
                    {t("builder.results.incomplete_pricing")}
                  </p>
                </TooltipTrigger>
                <TooltipContent>
                  {/* error_detail distinguishes a rate-card gap from a POA rule. */}
                  {option.error_detail ?? t("builder.results.incomplete_pricing_hint")}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant={isPropertyStaged(option.property_id) ? "secondary" : "outline"}
            disabled={isPropertyStaged(option.property_id)}
            onClick={() => onAdd(option)}
          >
            {isPropertyStaged(option.property_id)
              ? t("builder.results.added")
              : t("builder.results.add_manual")}
          </Button>
        </article>
      ))}

      {unavailable.length > 0 ? (
        <Collapsible
          className="border-border rounded-md border border-dashed"
          headerClassName="text-muted-foreground hover:text-foreground gap-2 p-3 text-sm"
          title={t("builder.results.unavailable_count", { count: unavailable.length })}
        >
          <div className="space-y-3 p-3 pt-0">
            {unavailable.map((option) => (
              <Tooltip key={option.property_id}>
                <TooltipTrigger asChild>
                  <article
                    className="border-border flex items-center justify-between gap-3 rounded-md border border-dashed p-3 opacity-60"
                    aria-label={t("builder.results.unavailable_aria", {
                      name: option.property_name,
                    })}
                  >
                    <div className="flex items-center gap-3">
                      <PropertyThumbnail
                        src={option.hero_image_url}
                        fallbackText={option.property_name}
                        alt={t("builder.results.thumbnail_alt", { name: option.property_name })}
                      />
                      <div>
                        <h4 className="text-foreground text-sm font-semibold">
                          {option.property_name}
                        </h4>
                        <OptionMeta option={option} />
                        <p className="text-muted-foreground text-xs">
                          {t("builder.results.unavailable")}
                        </p>
                      </div>
                    </div>
                  </article>
                </TooltipTrigger>
                <TooltipContent>
                  {option.error_code === "dates_unavailable"
                    ? t("builder.results.dates_unavailable_hint")
                    : (option.error_detail ??
                      option.error_code ??
                      t("builder.results.unavailable"))}
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </Collapsible>
      ) : null}

      {/* Pagination is over name-sorted candidates, not available results — a
          Load-more click prices the next page and may surface few (or no) new
          available villas. The count line makes that legible rather than
          looking like a no-op. */}
      <div className="flex flex-col items-center gap-2 pt-1">
        <p className="text-muted-foreground text-xs">
          {t("builder.results.priced_count", {
            available: available.length,
            priced: options.length,
            total: totalMatched,
          })}
        </p>
        {hasMore ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            disabled={isLoadingMore}
            onClick={onLoadMore}
          >
            {isLoadingMore ? t("builder.results.loading_more") : t("builder.results.load_more")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
