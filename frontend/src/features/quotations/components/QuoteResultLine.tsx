import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMoney } from "@/lib/format/money";
import { formatDate } from "@/lib/format/date";
import { useRepriceStayOption } from "../hooks";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { StayOptionPicker } from "./StayOptionPicker";
import type { ChosenStay, OccupancyBand, QuoteOption, StayReprice } from "../schemas";

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
  // GAP-044: a banded result also hands the checked occupancy bands to the
  // builder (consumed by a later unit); the third arg stays optional so
  // non-banded callers are unaffected.
  onAdd: (option: QuoteOption, stay?: ChosenStay, selectedBands?: OccupancyBand[]) => void;
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

  // GAP-044b two-axis picker: an occupancy-priced villa shows the *selected*
  // week's brackets (see `resolvedBands` below). The operator trims bands by
  // identity (party range), not array index, so a check survives a week flip
  // even if the bracket set reorders/resizes across seasonal cards. Track the
  // DESELECTED keys so a not-yet-seen bracket (a new week's) defaults to checked.
  const bandKey = (b: OccupancyBand) => `${b.min_party}-${b.max_party}`;
  const [deselectedBands, setDeselectedBands] = useState<Set<string>>(() => new Set());
  const isBandChecked = (b: OccupancyBand) => !deselectedBands.has(bandKey(b));
  const toggleBand = (b: OccupancyBand) =>
    setDeselectedBands((prev) => {
      const next = new Set(prev);
      const k = bandKey(b);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  const stayOptions = useMemo(() => option.stay_options ?? [], [option.stay_options]);
  const hasPicker = stayOptions.length > 1;
  const defaultIndex = Math.max(
    0,
    stayOptions.findIndex((o) => o.is_default),
  );
  // Default block preselected when it's free; otherwise the first free block
  // (the whole point of the alternatives); otherwise fall back to the default.
  // A banded villa now behaves identically (GAP-044b): its bands resolve per
  // week, so a held default preselects — and reprices — a free alternate.
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

  // GAP-044b: the SELECTED week's occupancy bands — read straight from the
  // default option or that week's cached reprice, decoupled from the reprice's
  // `available`. An out-of-bracket party (B2) reprices to available:false yet
  // still carries the full band array; gating bands on `resolved` (which
  // collapses !available to an error) would wrongly hide a saveable selection.
  const repriceEntry = !isDefaultSelected && selected ? reprices[selected.date_from] : undefined;
  const repriceObj: StayReprice | null =
    repriceEntry && repriceEntry !== "pending" && repriceEntry !== "error" ? repriceEntry : null;
  const resolvedBands = useMemo<OccupancyBand[]>(() => {
    if (isDefaultSelected) return option.occupancy_bands ?? [];
    return repriceObj?.occupancy_bands ?? [];
  }, [isDefaultSelected, option.occupancy_bands, repriceObj]);
  const isBandedView = resolvedBands.length > 0;
  const checkedSaveableBands = resolvedBands.filter(
    (b) => isBandChecked(b) && !b.is_poa && b.total != null,
  );

  // The dates the selected week actually priced at — kept independent of the
  // flat `resolved` path so a banded/out-of-bracket week still surfaces a shift.
  const selectedPricedFrom = isDefaultSelected
    ? (option.date_from ?? selected?.date_from ?? "")
    : (repriceObj?.date_from ?? selected?.date_from ?? "");
  const selectedPricedTo = isDefaultSelected
    ? (option.date_to ?? selected?.date_to ?? "")
    : (repriceObj?.date_to ?? selected?.date_to ?? "");

  // The engine can still nudge a repriced arrival (changeover rule boundary
  // inside the window) — never silently show different dates than clicked.
  // Dates are known for the default block, or once an alternate has repriced.
  const datesKnown = isDefaultSelected || repriceObj != null;
  const shifted =
    selected != null &&
    datesKnown &&
    (selectedPricedFrom !== selected.date_from || selectedPricedTo !== selected.date_to);

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
  // A booked (held) week can never be added, banded or not. Beyond that: a
  // banded week needs ≥1 saveable (non-POA, priced) checked band; a flat week
  // needs its price resolved (which also covers "still repricing"). `isBandedView`
  // follows the SELECTED week, so a villa banded in one season and flat in
  // another gates on whichever shape the chosen week resolved to.
  const addDisabled =
    staged ||
    heldSelected ||
    (isBandedView ? checkedSaveableBands.length === 0 : resolved.state !== "ready");

  const handleAdd = () => {
    // Carry the SELECTED week's stay whenever its dates are known: a flat week
    // needs a resolved price; a banded week rides on its bands, so a repriced
    // (or default) week is enough even out-of-bracket. A legacy option with no
    // stay_options hands over no stay (the builder falls back to the criteria).
    const priceReady = resolved.state === "ready";
    const stay: ChosenStay | undefined =
      selected && (isBandedView ? datesKnown : priceReady)
        ? {
            date_from: selected.date_from,
            date_to: selected.date_to,
            is_default: isDefaultSelected,
            priced_date_from: selectedPricedFrom || selected.date_from,
            priced_date_to: selectedPricedTo || selected.date_to,
            // A banded line takes its total/currency from the bands, never a
            // single figure (bands are alternatives) — leave them null.
            total: isBandedView ? null : priceReady ? resolved.total : null,
            currency: isBandedView ? null : priceReady ? resolved.currency : null,
            inclusion: priceReady ? resolved.inclusion : (option.inclusion ?? null),
          }
        : undefined;
    if (isBandedView) {
      onAdd(option, stay, resolvedBands.filter(isBandChecked));
    } else {
      onAdd(option, stay);
    }
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
          {isBandedView ? (
            <div className="space-y-1">
              <p className="text-foreground/80 text-xs font-medium">
                {t("builder.results.bands.heading")}
              </p>
              {resolvedBands.map((b, i) => (
                <CheckboxLabel
                  key={`${b.min_party}-${b.max_party}-${i}`}
                  className="justify-between"
                >
                  <span className="flex items-center gap-2">
                    <Checkbox checked={isBandChecked(b)} onCheckedChange={() => toggleBand(b)} />
                    <span className="text-muted-foreground text-xs">
                      {t("builder.results.bands.party_range", {
                        min: b.min_party,
                        max: b.max_party,
                      })}
                    </span>
                  </span>
                  <span className="text-foreground text-xs font-medium">
                    {b.is_poa || b.total == null
                      ? t("builder.results.bands.poa")
                      : // Per-band currency — a banded list can mix £/€/$.
                        formatMoney(b.total, b.currency_code)}
                  </span>
                </CheckboxLabel>
              ))}
            </div>
          ) : resolved.state === "error" ? (
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
                from: formatDate(selectedPricedFrom || null),
                to: formatDate(selectedPricedTo || null),
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
