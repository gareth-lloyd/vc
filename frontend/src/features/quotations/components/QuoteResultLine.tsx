import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMoney } from "@/lib/format/money";
import { formatDate } from "@/lib/format/date";
import { useRepriceStayOption } from "../hooks";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { StayOptionPicker } from "./StayOptionPicker";
import type { ChosenStay, QuoteOption, StayReprice } from "../schemas";

// Day codes the backend's PrefilledChangeOverDay can emit ("any" serialises
// as null). A closed set so we never build an i18n key from arbitrary input.
const DAY_CODES = new Set(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);

// Above this length the inclusions text collapses behind a Show-more toggle
// so a wordy plan doesn't dwarf the rest of the card.
const INCLUSIONS_CLAMP_CHARS = 140;

interface Props {
  option: QuoteOption;
  staged: boolean;
  // Party for block reprices — the criteria the search ran with.
  adults: number;
  children: number;
  onAdd: (option: QuoteOption, stay?: ChosenStay) => void;
}

// What the currently selected stay block resolves to: the option's own price
// for the default block, a cached reprice for a picked alternative.
type ResolvedPrice =
  | {
      state: "ready";
      total: string | number | null;
      currency: string | null;
      pricedFrom: string;
      pricedTo: string;
      inclusion: string | null;
    }
  | { state: "pending" }
  | { state: "error"; detail: string | null };

/**
 * Information-dense card for one priced (available) result: identity,
 * capacity + stay-constraint meta, pricing badges, the winning plan's
 * inclusions, the headline total — and, when the flexibility window admits
 * several changeover blocks, a block picker that reprices on pick.
 */
export function QuoteResultLine({ option, staged, adults, children, onAdd }: Props) {
  const { t } = useTranslation("quotations");
  const [inclusionsExpanded, setInclusionsExpanded] = useState(false);

  const stayOptions = useMemo(() => option.stay_options ?? [], [option.stay_options]);
  const hasPicker = stayOptions.length > 1;
  const defaultIndex = Math.max(
    0,
    stayOptions.findIndex((o) => o.is_default),
  );
  // Default block preselected when it's free; otherwise the first free block
  // (the whole point of the alternatives); otherwise fall back to the default.
  const [selectedIndex, setSelectedIndex] = useState(() => {
    if (!hasPicker || stayOptions[defaultIndex]?.is_available) return defaultIndex;
    const firstAvailable = stayOptions.findIndex((o) => o.is_available);
    return firstAvailable === -1 ? defaultIndex : firstAvailable;
  });
  // Per-block reprice cache, keyed by arrival date. Row-local on purpose: a
  // fresh search remounts the row (the parent keys it on the criteria), which
  // is exactly when these prices go stale.
  const [reprices, setReprices] = useState<Record<string, StayReprice | "pending" | "error">>({});
  const reprice = useRepriceStayOption();
  const repriceMutate = reprice.mutate;

  const selected = stayOptions[selectedIndex];
  const isDefaultSelected = !hasPicker || selectedIndex === defaultIndex;

  // A non-default block has no up-front price — fetch it once on selection
  // (this also covers a held default whose first-free alternative is
  // preselected on mount).
  useEffect(() => {
    if (!selected || isDefaultSelected) return;
    const key = selected.date_from;
    if (reprices[key] !== undefined) return;
    setReprices((prev) => ({ ...prev, [key]: "pending" }));
    repriceMutate(
      {
        property_id: option.property_id,
        date_from: selected.date_from,
        date_to: selected.date_to,
        adults,
        children,
      },
      {
        onSuccess: (result) => setReprices((prev) => ({ ...prev, [key]: result })),
        onError: () => setReprices((prev) => ({ ...prev, [key]: "error" })),
      },
    );
  }, [selected, isDefaultSelected, reprices, repriceMutate, option.property_id, adults, children]);

  const resolved: ResolvedPrice = useMemo(() => {
    if (!selected || isDefaultSelected) {
      return {
        state: "ready",
        total: option.total ?? null,
        currency: option.currency ?? null,
        pricedFrom: option.date_from ?? selected?.date_from ?? "",
        pricedTo: option.date_to ?? selected?.date_to ?? "",
        inclusion: option.inclusion ?? null,
      };
    }
    const entry = reprices[selected.date_from];
    if (entry === undefined || entry === "pending") return { state: "pending" };
    if (entry === "error") return { state: "error", detail: null };
    if (!entry.available) {
      return { state: "error", detail: entry.error_detail ?? entry.error_code ?? null };
    }
    return {
      state: "ready",
      total: entry.total ?? null,
      currency: entry.currency_code ?? null,
      pricedFrom: entry.date_from ?? selected.date_from,
      pricedTo: entry.date_to ?? selected.date_to,
      inclusion: entry.inclusion ?? option.inclusion ?? null,
    };
  }, [selected, isDefaultSelected, reprices, option]);

  // The engine can still nudge a repriced arrival (changeover rule boundary
  // inside the window) — never silently show different dates than clicked.
  const shifted =
    selected != null &&
    resolved.state === "ready" &&
    (resolved.pricedFrom !== selected.date_from || resolved.pricedTo !== selected.date_to);

  const metaParts: string[] = [];
  if (option.internal_name && option.internal_name !== option.property_name) {
    metaParts.push(option.internal_name);
  }
  if (option.bedrooms != null) {
    metaParts.push(t("builder.results.bedrooms", { count: option.bedrooms }));
  }
  if (option.sleeps != null) {
    metaParts.push(t("builder.results.sleeps", { count: option.sleeps }));
  }
  if (option.changeover_day && DAY_CODES.has(option.changeover_day)) {
    metaParts.push(
      t("builder.results.changeover_day", {
        day: t(`builder.results.days.${option.changeover_day}`),
      }),
    );
  } else if (option.changeover_day === null && option.min_nights != null) {
    // Only meaningful next to other stay constraints — an enrichment-less
    // legacy response (both fields absent) shouldn't claim "no fixed day".
    metaParts.push(t("builder.results.no_fixed_changeover"));
  }
  if (option.min_nights != null && option.min_nights > 1) {
    metaParts.push(t("builder.results.min_nights", { count: option.min_nights }));
  }

  const inclusions = option.inclusion?.trim() ?? "";
  const inclusionsClamped = inclusions.length > INCLUSIONS_CLAMP_CHARS;
  const inclusionsShown =
    inclusionsClamped && !inclusionsExpanded
      ? `${inclusions.slice(0, INCLUSIONS_CLAMP_CHARS).trimEnd()}…`
      : inclusions;

  const heldSelected = selected != null && !selected.is_available;
  const addDisabled = staged || heldSelected || resolved.state !== "ready";

  const handleAdd = () => {
    const stay: ChosenStay | undefined =
      selected && resolved.state === "ready"
        ? {
            date_from: selected.date_from,
            date_to: selected.date_to,
            is_default: isDefaultSelected,
            priced_date_from: resolved.pricedFrom || selected.date_from,
            priced_date_to: resolved.pricedTo || selected.date_to,
            total: resolved.total,
            currency: resolved.currency,
            inclusion: resolved.inclusion,
          }
        : undefined;
    onAdd(option, stay);
  };

  const addButton = (
    <Button
      type="button"
      size="sm"
      variant={staged ? "secondary" : "default"}
      disabled={addDisabled}
      onClick={handleAdd}
    >
      {staged ? t("builder.results.added") : t("builder.results.add")}
    </Button>
  );

  return (
    <article className="border-border flex items-start justify-between gap-3 rounded-md border p-3">
      <div className="flex items-start gap-3">
        <PropertyThumbnail
          src={option.hero_image_url}
          fallbackText={option.property_name}
          alt={t("builder.results.thumbnail_alt", { name: option.property_name })}
        />
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-foreground text-sm font-semibold">{option.property_name}</h4>
            {option.occupancy_pricing ? (
              <StatusBadge
                status="occupancy_pricing"
                kind="pending"
                label={t("builder.results.occupancy_pricing")}
              />
            ) : null}
            {option.is_projected ? (
              <StatusBadge status="projected" kind="draft" label={t("builder.results.projected")} />
            ) : null}
          </div>
          {metaParts.length > 0 ? (
            <p className="text-muted-foreground text-xs">{metaParts.join(" · ")}</p>
          ) : null}
          {inclusions ? (
            <p className="text-muted-foreground text-xs">
              <span className="text-foreground/80 font-medium">
                {t("builder.results.inclusions_label")}:
              </span>{" "}
              {inclusionsShown}
              {inclusionsClamped ? (
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0 pl-1 text-xs"
                  onClick={() => setInclusionsExpanded((v) => !v)}
                >
                  {inclusionsExpanded
                    ? t("builder.results.inclusions_less")
                    : t("builder.results.inclusions_more")}
                </Button>
              ) : null}
            </p>
          ) : null}
          {hasPicker ? (
            <StayOptionPicker
              options={stayOptions}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          ) : null}
          {resolved.state === "error" ? (
            <p className="text-destructive text-xs" role="alert">
              {resolved.detail ?? t("builder.results.stay_options.reprice_failed")}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              {t("builder.results.total")}:{" "}
              <span className="text-foreground font-medium">
                {resolved.state === "pending"
                  ? t("builder.results.stay_options.repricing")
                  : // Per-result currency (GAP-014) — one list freely mixes £/€/$.
                    formatMoney(resolved.total, resolved.currency)}
              </span>
            </p>
          )}
          {shifted ? (
            <p className="text-warning text-xs">
              {t("builder.results.stay_options.shifted", {
                from: formatDate(resolved.state === "ready" ? resolved.pricedFrom : null),
                to: formatDate(resolved.state === "ready" ? resolved.pricedTo : null),
              })}
            </p>
          ) : null}
        </div>
      </div>
      {heldSelected ? (
        <Tooltip>
          {/* span wrapper: a disabled button can't anchor a tooltip. */}
          <TooltipTrigger asChild>
            <span tabIndex={0}>{addButton}</span>
          </TooltipTrigger>
          <TooltipContent>{t("builder.results.stay_options.held_hint")}</TooltipContent>
        </Tooltip>
      ) : (
        addButton
      )}
    </article>
  );
}
