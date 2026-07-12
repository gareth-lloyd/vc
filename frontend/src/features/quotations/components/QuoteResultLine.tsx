import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMoneyWithCode } from "@/lib/format/money";
import { formatDate, formatWeekRangeCompact } from "@/lib/format/date";
import { useRepriceStayOption } from "../hooks";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { StayOptionPicker } from "./StayOptionPicker";
import {
  type ChosenStay,
  type OccupancyBand,
  type QuoteOption,
  type StayAdd,
  type StayReprice,
  stagedLineId,
  stagedStayDates,
} from "../schemas";

// Day codes the backend's PrefilledChangeOverDay can emit ("any" serialises
// as null). A closed set so we never build an i18n key from arbitrary input.
const DAY_CODES = new Set(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);

// Above this length the inclusions text collapses behind a Show-more toggle
// so a wordy plan doesn't dwarf the rest of the card.
const INCLUSIONS_CLAMP_CHARS = 140;

interface Props {
  option: QuoteOption;
  // Staged line_ids — the per-week Added markers and add gating derive from
  // these (GAP-043).
  stagedKeys: Set<string>;
  // The dates the search ran with — needed to map each week cell onto the
  // line identity the builder would stage it under (stagedStayDates).
  criteriaDates: { date_from: string; date_to: string };
  // Party for block reprices — the criteria the search ran with.
  adults: number;
  children: number;
  // GAP-043: one add-unit per checked, addable week; a banded week's unit
  // carries that week's checked occupancy bands (GAP-044).
  onAdd: (option: QuoteOption, adds?: StayAdd[]) => void;
}

// What a checked stay block resolves to: the option's own price for the
// default block, a cached reprice for any other week.
type ResolvedPrice =
  | {
      state: "ready";
      total: string | number | null;
      // Q-018: the pre-reduction total when the engine quoted reduced prices
      // — renders as a muted "reduced from" hint next to the effective total.
      totalBeforeReduction: string | number | null;
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
 * inclusions, per-week pricing — and, when the flexibility window admits
 * several changeover blocks, a multi-select week picker (GAP-043): every
 * checked week is repriced and becomes its own quote line on Add.
 */
export function QuoteResultLine({
  option,
  stagedKeys,
  criteriaDates,
  adults,
  children,
  onAdd,
}: Props) {
  const { t } = useTranslation("quotations");
  const [inclusionsExpanded, setInclusionsExpanded] = useState(false);

  // GAP-044b: an occupancy-priced villa shows the lead banded week's brackets
  // (see `leadBands` below). The operator trims bands by identity (party
  // range), not array index, so a check survives across weeks even if the
  // bracket set reorders/resizes across seasonal cards; the same shared check
  // set applies to EVERY checked week (GAP-043 decision: one band-check,
  // cross-product with weeks). Track the DESELECTED keys so a not-yet-seen
  // bracket (another week's) defaults to checked.
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
  // Default block pre-checked when it's free; otherwise the first free block
  // (the whole point of the alternatives); otherwise nothing. Starting from a
  // single check keeps mount to ≤1 reprice.
  const [checkedIndices, setCheckedIndices] = useState<Set<number>>(() => {
    if (stayOptions.length === 0) return new Set();
    if (stayOptions[defaultIndex]?.is_available) return new Set([defaultIndex]);
    const firstAvailable = stayOptions.findIndex((o) => o.is_available);
    return firstAvailable === -1 ? new Set() : new Set([firstAvailable]);
  });
  const toggleWeek = (index: number) =>
    setCheckedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  const checkedSorted = useMemo(
    () => Array.from(checkedIndices).sort((a, b) => a - b),
    [checkedIndices],
  );

  // Per-block reprice cache, keyed by arrival date. Row-local on purpose: a
  // fresh search remounts the row (the parent keys it on the criteria), which
  // is exactly when these prices go stale.
  const [reprices, setReprices] = useState<Record<string, StayReprice | "pending" | "error">>({});
  const reprice = useRepriceStayOption();
  const repriceMutate = reprice.mutate;

  // Any checked non-default week has no up-front price — fetch each once when
  // checked (the per-key guard stops re-fires and loops; unchecking keeps the
  // cache warm for a re-check).
  useEffect(() => {
    for (const index of checkedIndices) {
      if (index === defaultIndex) continue;
      const block = stayOptions[index];
      if (!block) continue;
      const key = block.date_from;
      if (reprices[key] !== undefined) continue;
      setReprices((prev) => ({ ...prev, [key]: "pending" }));
      repriceMutate(
        {
          property_id: option.property_id,
          date_from: block.date_from,
          date_to: block.date_to,
          adults,
          children,
        },
        {
          onSuccess: (result) => setReprices((prev) => ({ ...prev, [key]: result })),
          onError: () => setReprices((prev) => ({ ...prev, [key]: "error" })),
        },
      );
    }
  }, [
    checkedIndices,
    defaultIndex,
    stayOptions,
    reprices,
    repriceMutate,
    option.property_id,
    adults,
    children,
  ]);

  // The successful reprice object for a week, or null (default week: null —
  // its pricing lives on the option itself).
  const repriceFor = (index: number): StayReprice | null => {
    if (index === defaultIndex) return null;
    const block = stayOptions[index];
    const entry = block ? reprices[block.date_from] : undefined;
    return entry && entry !== "pending" && entry !== "error" ? entry : null;
  };

  const resolveWeek = (index: number): ResolvedPrice => {
    const block = stayOptions[index];
    if (index === defaultIndex || !block) {
      return {
        state: "ready",
        total: option.total ?? null,
        totalBeforeReduction: option.total_before_reduction ?? null,
        currency: option.currency ?? null,
        pricedFrom: option.date_from ?? block?.date_from ?? "",
        pricedTo: option.date_to ?? block?.date_to ?? "",
        inclusion: option.inclusion ?? null,
      };
    }
    const entry = reprices[block.date_from];
    if (entry === undefined || entry === "pending") return { state: "pending" };
    if (entry === "error") return { state: "error", detail: null };
    if (!entry.available) {
      return { state: "error", detail: entry.error_detail ?? entry.error_code ?? null };
    }
    return {
      state: "ready",
      total: entry.total ?? null,
      totalBeforeReduction: entry.total_before_reduction ?? null,
      currency: entry.currency_code ?? null,
      pricedFrom: entry.date_from ?? block.date_from,
      pricedTo: entry.date_to ?? block.date_to,
      inclusion: entry.inclusion ?? option.inclusion ?? null,
    };
  };

  // GAP-044b: a week's occupancy bands — from the option for the default
  // block, from that week's cached reprice otherwise. Read independently of
  // `resolveWeek` (which collapses !available to an error): an out-of-bracket
  // party (B2) reprices to available:false yet still carries the full band
  // array, and gating bands on it would wrongly hide a saveable selection.
  const bandsForWeek = (index: number): OccupancyBand[] => {
    if (index === defaultIndex) return option.occupancy_bands ?? [];
    return repriceFor(index)?.occupancy_bands ?? [];
  };
  // Whether a week's dates/bands are known — the default block always, an
  // alternate once its reprice returned (even out-of-bracket).
  const weekKnown = (index: number): boolean => index === defaultIndex || repriceFor(index) != null;

  // The dates a week actually priced at (may be changeover-shifted).
  const pricedRange = (index: number): { from: string; to: string } => {
    const block = stayOptions[index];
    if (index === defaultIndex) {
      return {
        from: option.date_from ?? block?.date_from ?? "",
        to: option.date_to ?? block?.date_to ?? "",
      };
    }
    const entry = repriceFor(index);
    return {
      from: entry?.date_from ?? block?.date_from ?? "",
      to: entry?.date_to ?? block?.date_to ?? "",
    };
  };

  // No-stay-options results (legacy, or a flexible-changeover villa): the card
  // has no picker and stages on the criteria dates.
  const hasBlocks = stayOptions.length > 0;
  const leadBands = hasBlocks
    ? bandsForWeek(
        checkedSorted.find((i) => bandsForWeek(i).length > 0) ?? checkedSorted[0] ?? defaultIndex,
      )
    : (option.occupancy_bands ?? []);
  const isBandedView = leadBands.length > 0;
  const checkedSaveableBands = leadBands.filter(
    (b) => isBandChecked(b) && !b.is_poa && b.total != null,
  );

  // Per-week staged markers: map each block onto the line identity the
  // builder would stage it under (same helper ⇒ same key, GAP-007 included).
  // Plain per-render computation — a handful of cheap set lookups.
  const stagedIndices = new Set<number>();
  stayOptions.forEach((block, index) => {
    const key = stagedLineId(option.property_id, stagedStayDates(criteriaDates, block).date_from);
    if (stagedKeys.has(key)) stagedIndices.add(index);
  });
  const noStayStaged = stagedKeys.has(stagedLineId(option.property_id, criteriaDates.date_from));

  // A week the Add button would actually stage: checked, bookable, not yet
  // staged, and priced — a banded week needs its bands known and ≥1 saveable
  // checked band; a flat week needs its price resolved.
  const weekAddable = (index: number): boolean => {
    const block = stayOptions[index];
    if (!block?.is_available || stagedIndices.has(index)) return false;
    const bands = bandsForWeek(index);
    if (bands.length > 0) {
      return bands.some((b) => isBandChecked(b) && !b.is_poa && b.total != null);
    }
    // A checked week that is still repricing may yet come back banded — not
    // addable until it resolves either way.
    return weekKnown(index) && resolveWeek(index).state === "ready";
  };

  const addableIndices = hasBlocks ? checkedSorted.filter(weekAddable) : [];
  // No blocks: the single criteria-dates add, gated like the old card.
  const noBlocksAddable =
    !noStayStaged && (isBandedView ? checkedSaveableBands.length > 0 : option.total != null);
  const addableCount = hasBlocks ? addableIndices.length : noBlocksAddable ? 1 : 0;

  // Held gating: with a picker, held cells simply can't be checked; without
  // one, a held single block keeps its explanatory tooltip.
  const singleBlockHeld = !hasPicker && hasBlocks && !stayOptions[0].is_available;

  // A checked, bookable, unstaged week still waiting on its reprice — the
  // card is loading, not done, so it must not read "Added" yet.
  const anyCheckedPending =
    hasBlocks &&
    checkedSorted.some((i) => {
      const block = stayOptions[i];
      return block?.is_available === true && !stagedIndices.has(i) && !weekKnown(i);
    });

  const stagedOut =
    addableCount === 0 &&
    !anyCheckedPending &&
    (hasBlocks ? checkedSorted.some((i) => stagedIndices.has(i)) : noStayStaged);

  const addDisabled = addableCount === 0 || singleBlockHeld;

  const buildStay = (index: number): ChosenStay => {
    const block = stayOptions[index];
    const resolved = resolveWeek(index);
    const priceReady = resolved.state === "ready";
    const banded = bandsForWeek(index).length > 0;
    const priced = pricedRange(index);
    return {
      date_from: block.date_from,
      date_to: block.date_to,
      is_default: index === defaultIndex,
      priced_date_from: priced.from || block.date_from,
      priced_date_to: priced.to || block.date_to,
      // A banded line takes its total/currency from the bands, never a
      // single figure (bands are alternatives) — leave them null.
      total: banded ? null : priceReady ? resolved.total : null,
      currency: banded ? null : priceReady ? resolved.currency : null,
      inclusion: priceReady ? resolved.inclusion : (option.inclusion ?? null),
    };
  };

  const handleAdd = () => {
    if (!hasBlocks) {
      // Legacy/blockless: one criteria-dates line; a banded villa rides on its
      // checked bands (GAP-044), a flat one on the option's own price.
      onAdd(option, isBandedView ? [{ bands: leadBands.filter(isBandChecked) }] : undefined);
      return;
    }
    const adds: StayAdd[] = addableIndices.map((index) => {
      const bands = bandsForWeek(index);
      return bands.length > 0
        ? { stay: buildStay(index), bands: bands.filter(isBandChecked) }
        : { stay: buildStay(index) };
    });
    if (adds.length === 0) return;
    onAdd(option, adds);
  };

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

  // Shift notes: a week whose priced dates differ from its block (the engine
  // nudged the arrival inside the window) — per checked week, once known.
  const shiftedWeeks = hasBlocks
    ? checkedSorted.filter((index) => {
        const block = stayOptions[index];
        if (!block || !weekKnown(index)) return false;
        const priced = pricedRange(index);
        return priced.from !== block.date_from || priced.to !== block.date_to;
      })
    : [];

  // Q-018: muted "reduced from" hint appended after an effective price when
  // the engine applied a rate reduction. Null when there was no reduction —
  // or no currency: formatMoneyWithCode falls back to an em-dash then, and a
  // "reduced from —" next to an already-dashed price is pure noise.
  const reducedFromHint = (
    before: string | number | null | undefined,
    currency: string | null | undefined,
  ) =>
    before != null && currency ? (
      <span className="text-muted-foreground font-normal">
        {" · "}
        {t("builder.results.reduced_from", {
          amount: formatMoneyWithCode(before, currency),
        })}
      </span>
    ) : null;

  // Per-week price row content for the picker view.
  const weekRow = (index: number) => {
    const block = stayOptions[index];
    const banded = bandsForWeek(index).length > 0;
    const resolved = resolveWeek(index);
    let value: React.ReactNode;
    if (banded) {
      value = (
        <span className="text-muted-foreground">{t("builder.results.occupancy_pricing")}</span>
      );
    } else if (resolved.state === "pending") {
      value = (
        <span className="text-muted-foreground">{t("builder.results.stay_options.repricing")}</span>
      );
    } else if (resolved.state === "error") {
      value = (
        <span className="text-destructive" role="alert">
          {resolved.detail ?? t("builder.results.stay_options.reprice_failed")}
        </span>
      );
    } else {
      value = (
        <span className="text-foreground font-medium">
          {formatMoneyWithCode(resolved.total, resolved.currency)}
          {reducedFromHint(resolved.totalBeforeReduction, resolved.currency)}
        </span>
      );
    }
    return (
      <p key={block.date_from} className="text-muted-foreground text-xs">
        {formatWeekRangeCompact(block.date_from, block.date_to)}: {value}
      </p>
    );
  };

  const addButton = (
    <Button
      type="button"
      size="sm"
      variant={stagedOut ? "secondary" : "default"}
      disabled={addDisabled}
      onClick={handleAdd}
    >
      {stagedOut
        ? t("builder.results.added")
        : addableCount > 1
          ? t("builder.results.add_count", { count: addableCount })
          : t("builder.results.add")}
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
              checkedIndices={checkedIndices}
              onToggle={toggleWeek}
              stagedIndices={stagedIndices}
            />
          ) : null}
          {hasPicker ? checkedSorted.map(weekRow) : null}
          {isBandedView ? (
            <div className="space-y-1">
              <p className="text-foreground/80 text-xs font-medium">
                {t("builder.results.bands.heading")}
              </p>
              {leadBands.map((b, i) => (
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
                    {b.is_poa || b.total == null ? (
                      t("builder.results.bands.poa")
                    ) : (
                      <>
                        {/* Per-band currency — a banded list can mix £/€/$. */}
                        {formatMoneyWithCode(b.total, b.currency_code)}
                        {reducedFromHint(b.total_before_reduction, b.currency_code)}
                      </>
                    )}
                  </span>
                </CheckboxLabel>
              ))}
            </div>
          ) : null}
          {!hasPicker && !isBandedView
            ? (() => {
                const resolved = resolveWeek(defaultIndex);
                if (resolved.state === "error") {
                  return (
                    <p className="text-destructive text-xs" role="alert">
                      {resolved.detail ?? t("builder.results.stay_options.reprice_failed")}
                    </p>
                  );
                }
                return (
                  <p className="text-muted-foreground text-xs">
                    {t("builder.results.total")}:{" "}
                    <span className="text-foreground font-medium">
                      {resolved.state === "pending" ? (
                        t("builder.results.stay_options.repricing")
                      ) : (
                        <>
                          {/* Per-result currency (GAP-014) — one list mixes £/€/$. */}
                          {formatMoneyWithCode(resolved.total, resolved.currency)}
                          {reducedFromHint(resolved.totalBeforeReduction, resolved.currency)}
                        </>
                      )}
                    </span>
                  </p>
                );
              })()
            : null}
          {shiftedWeeks.map((index) => {
            const priced = pricedRange(index);
            return (
              <p key={`shift-${stayOptions[index].date_from}`} className="text-warning text-xs">
                {t("builder.results.stay_options.shifted", {
                  from: formatDate(priced.from || null),
                  to: formatDate(priced.to || null),
                })}
              </p>
            );
          })}
        </div>
      </div>
      {singleBlockHeld ? (
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
