import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatMoney } from "@/lib/format/money";
import { PropertyThumbnail } from "./PropertyThumbnail";
import type { QuoteOption } from "../schemas";

// Day codes the backend's PrefilledChangeOverDay can emit ("any" serialises
// as null). A closed set so we never build an i18n key from arbitrary input.
const DAY_CODES = new Set(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);

// Above this length the inclusions text collapses behind a Show-more toggle
// so a wordy plan doesn't dwarf the rest of the card.
const INCLUSIONS_CLAMP_CHARS = 140;

interface Props {
  option: QuoteOption;
  staged: boolean;
  onAdd: (option: QuoteOption) => void;
}

/**
 * Information-dense card for one priced (available) result: identity,
 * capacity + stay-constraint meta, pricing badges, the winning plan's
 * inclusions, and the headline total.
 */
export function QuoteResultLine({ option, staged, onAdd }: Props) {
  const { t } = useTranslation("quotations");
  const [inclusionsExpanded, setInclusionsExpanded] = useState(false);

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
          <p className="text-muted-foreground text-xs">
            {t("builder.results.total")}:{" "}
            <span className="text-foreground font-medium">
              {/* Per-result currency (GAP-014) — one list freely mixes £/€/$. */}
              {formatMoney(option.total ?? null, option.currency ?? null)}
            </span>
          </p>
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        variant={staged ? "secondary" : "default"}
        disabled={staged}
        onClick={() => onAdd(option)}
      >
        {staged ? t("builder.results.added") : t("builder.results.add")}
      </Button>
    </article>
  );
}
