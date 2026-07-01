import { differenceInCalendarDays, parseISO } from "date-fns";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatMoney } from "@/lib/format/money";
import { formatDate } from "@/lib/format/date";
import { lineEffectiveTotal, stagedLineErrors } from "../lineTotals";
import type { StagedLine } from "../schemas";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { ChangeoverShiftedNote } from "./ChangeoverShiftedNote";

interface Props {
  line: StagedLine;
  expanded: boolean;
  onToggle: () => void;
  onUpdate: (patch: Partial<StagedLine>) => void;
  onRemove: () => void;
}

function nightCount(line: StagedLine): number {
  const from = parseISO(line.priced_date_from);
  const to = parseISO(line.priced_date_to);
  const nights = differenceInCalendarDays(to, from);
  return Number.isFinite(nights) && nights > 0 ? nights : 0;
}

export function QuoteShortlistLine({ line, expanded, onToggle, onUpdate, onRemove }: Props) {
  const { t } = useTranslation("quotations");
  const nights = nightCount(line);
  const effective = lineEffectiveTotal(line);

  // Per-field validity comes from the single canonical predicate, so the inline
  // errors here and the Save gate in SaveQuoteDialog agree on every input.
  const errors = stagedLineErrors(line);

  // GAP-044: a banded villa renders its occupancy brackets as a checkable priced
  // list IN PLACE OF a single total (bands are alternatives, never summed). A
  // manual override doesn't apply — each band is priced per bracket server-side.
  const bands = line.occupancy_bands;
  const banded = bands != null;
  const toggleBand = (index: number) => {
    if (!bands) return;
    onUpdate({
      occupancy_bands: bands.map((b, i) => (i === index ? { ...b, checked: !b.checked } : b)),
    });
  };

  const fieldId = (suffix: string) => `qcl-${line.property_id}-${suffix}`;

  return (
    <article className="border-border bg-card rounded-md border">
      <div className="flex items-start gap-3 p-3">
        <PropertyThumbnail
          src={line.hero_image_url}
          fallbackText={line.property_name}
          alt={t("builder.shortlist.thumbnail_alt", { name: line.property_name })}
        />
        <div className="min-w-0 flex-1">
          <h4 className="text-foreground truncate text-sm font-semibold">{line.property_name}</h4>
          <p className="text-muted-foreground text-xs">
            {formatDate(line.priced_date_from)} – {formatDate(line.priced_date_to)}
          </p>
          {banded ? (
            <p className="text-muted-foreground text-xs">
              {t("builder.shortlist.line.nights", { count: nights })} ·{" "}
              {t("builder.shortlist.line.guests", {
                adults: line.adults,
                children: line.children,
              })}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              {t("builder.shortlist.line.nights", { count: nights })} ·{" "}
              {t("builder.shortlist.line.guests", {
                adults: line.adults,
                children: line.children,
              })}{" "}
              ·{" "}
              <span className="text-foreground font-medium">
                {/* Each line formats in its own priced currency (GAP-014). */}
                {effective == null ? "—" : formatMoney(effective, line.currency)}
              </span>
            </p>
          )}
          {banded && bands ? (
            <div className="mt-1 space-y-1">
              <p className="text-foreground/80 text-xs font-medium">
                {t("builder.results.bands.heading")}
              </p>
              {bands.map((b, i) => (
                <CheckboxLabel
                  key={`${b.min_party}-${b.max_party}-${i}`}
                  className="justify-between"
                >
                  <span className="flex items-center gap-2">
                    <Checkbox
                      checked={b.checked}
                      aria-label={t("builder.shortlist.line.band_include", {
                        min: b.min_party,
                        max: b.max_party,
                      })}
                      onCheckedChange={() => toggleBand(i)}
                    />
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
                      : formatMoney(b.total, b.currency)}
                  </span>
                </CheckboxLabel>
              ))}
            </div>
          ) : null}
          {errors.total && (banded || !line.is_manual) ? (
            <p className="text-destructive text-xs" role="alert">
              {t(errors.total)}
            </p>
          ) : null}
          <ChangeoverShiftedNote
            from={line.priced_date_from !== line.date_from ? line.date_from : null}
            className="mt-0.5"
          />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label={expanded ? t("builder.shortlist.collapse") : t("builder.shortlist.edit")}
            aria-expanded={expanded}
            onClick={onToggle}
          >
            {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onRemove}>
            {t("builder.shortlist.line.remove")}
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="border-border space-y-4 border-t p-3">
          {/* A banded line has no single total to discount — each band is priced
              per bracket server-side, so the discount field is suppressed. */}
          {banded ? null : (
            <div className="space-y-2">
              <Label htmlFor={fieldId("discount")}>{t("builder.shortlist.line.discount")}</Label>
              <Input
                id={fieldId("discount")}
                type="text"
                inputMode="decimal"
                value={line.discount}
                disabled={line.is_manual}
                aria-invalid={errors.discount != null}
                onChange={(e) => onUpdate({ discount: e.target.value })}
              />
              {errors.discount ? (
                <p className="text-destructive text-xs" role="alert">
                  {t(errors.discount)}
                </p>
              ) : (
                <p className="text-muted-foreground text-xs">
                  {line.is_manual
                    ? t("builder.shortlist.line.discount_manual_hint")
                    : t("builder.shortlist.line.discount_hint")}
                </p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor={fieldId("inclusions")}>{t("builder.shortlist.line.inclusions")}</Label>
            <Textarea
              id={fieldId("inclusions")}
              rows={2}
              placeholder={t("builder.shortlist.line.inclusions_placeholder")}
              value={line.inclusions}
              onChange={(e) => onUpdate({ inclusions: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <CheckboxLabel>
              {/* A no-rate line has no engine total to fall back to: un-ticking
                  would strand it permanently invalid, so the box locks on. A
                  banded line is priced per bracket, so a manual override — which
                  replaces one total — makes no sense; the box is disabled. */}
              <Checkbox
                checked={line.is_manual}
                disabled={line.manual_only || banded}
                onCheckedChange={(v) => onUpdate({ is_manual: v === true })}
              />
              <span>{t("builder.shortlist.line.manual")}</span>
            </CheckboxLabel>
            <p className="text-muted-foreground text-xs">
              {banded
                ? t("builder.shortlist.line.manual_banded_hint")
                : line.manual_only
                  ? t("builder.shortlist.line.manual_locked_hint")
                  : t("builder.shortlist.line.manual_hint")}
            </p>
          </div>

          {line.is_manual ? (
            <>
              <div className="space-y-2">
                <Label htmlFor={fieldId("total")}>{t("builder.shortlist.line.total")}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id={fieldId("total")}
                    type="text"
                    inputMode="decimal"
                    value={line.total == null ? "" : String(line.total)}
                    aria-invalid={errors.total != null}
                    onChange={(e) => onUpdate({ total: e.target.value })}
                  />
                  {line.currency ? (
                    <span className="text-muted-foreground shrink-0 text-sm">{line.currency}</span>
                  ) : null}
                </div>
                {errors.total ? (
                  <p className="text-destructive text-xs" role="alert">
                    {t(errors.total)}
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor={fieldId("reason")}>{t("builder.shortlist.line.reason")}</Label>
                <Textarea
                  id={fieldId("reason")}
                  rows={2}
                  placeholder={t("builder.shortlist.line.reason_placeholder")}
                  value={line.price_override_reason}
                  aria-invalid={errors.reason != null}
                  onChange={(e) => onUpdate({ price_override_reason: e.target.value })}
                />
                {errors.reason ? (
                  <p className="text-destructive text-xs" role="alert">
                    {t(errors.reason)}
                  </p>
                ) : null}
              </div>
            </>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor={fieldId("note")}>{t("builder.shortlist.line.note")}</Label>
            <Textarea
              id={fieldId("note")}
              rows={2}
              value={line.notes}
              onChange={(e) => onUpdate({ notes: e.target.value })}
            />
          </div>
        </div>
      ) : null}
    </article>
  );
}
