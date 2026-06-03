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
  currency: string;
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

export function QuoteCartLine({ line, currency, expanded, onToggle, onUpdate, onRemove }: Props) {
  const { t } = useTranslation("quotations");
  const nights = nightCount(line);
  const effective = lineEffectiveTotal(line);

  // Per-field validity comes from the single canonical predicate, so the inline
  // errors here and the Save gate in SaveQuoteDialog agree on every input.
  const errors = stagedLineErrors(line);

  const fieldId = (suffix: string) => `qcl-${line.property_id}-${suffix}`;

  return (
    <article className="border-border bg-card rounded-md border">
      <div className="flex items-start gap-3 p-3">
        <PropertyThumbnail
          src={line.hero_image_url}
          fallbackText={line.property_name}
          alt={t("builder.cart.thumbnail_alt", { name: line.property_name })}
        />
        <div className="min-w-0 flex-1">
          <h4 className="text-foreground truncate text-sm font-semibold">{line.property_name}</h4>
          <p className="text-muted-foreground text-xs">
            {formatDate(line.priced_date_from)} – {formatDate(line.priced_date_to)}
          </p>
          <p className="text-muted-foreground text-xs">
            {t("builder.cart.line.nights", { count: nights })} ·{" "}
            {t("builder.cart.line.guests", { adults: line.adults, children: line.children })} ·{" "}
            <span className="text-foreground font-medium">
              {effective == null ? "—" : formatMoney(effective, currency)}
            </span>
          </p>
          {!line.is_manual && errors.total ? (
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
            aria-label={expanded ? t("builder.cart.collapse") : t("builder.cart.edit")}
            aria-expanded={expanded}
            onClick={onToggle}
          >
            {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onRemove}>
            {t("builder.cart.line.remove")}
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="border-border space-y-4 border-t p-3">
          <div className="space-y-2">
            <Label htmlFor={fieldId("discount")}>{t("builder.cart.line.discount")}</Label>
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
                  ? t("builder.cart.line.discount_manual_hint")
                  : t("builder.cart.line.discount_hint")}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor={fieldId("inclusions")}>{t("builder.cart.line.inclusions")}</Label>
            <Textarea
              id={fieldId("inclusions")}
              rows={2}
              placeholder={t("builder.cart.line.inclusions_placeholder")}
              value={line.inclusions}
              onChange={(e) => onUpdate({ inclusions: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <CheckboxLabel>
              <Checkbox
                checked={line.is_manual}
                onCheckedChange={(v) => onUpdate({ is_manual: v === true })}
              />
              <span>{t("builder.cart.line.manual")}</span>
            </CheckboxLabel>
            <p className="text-muted-foreground text-xs">{t("builder.cart.line.manual_hint")}</p>
          </div>

          {line.is_manual ? (
            <>
              <div className="space-y-2">
                <Label htmlFor={fieldId("total")}>{t("builder.cart.line.total")}</Label>
                <Input
                  id={fieldId("total")}
                  type="text"
                  inputMode="decimal"
                  value={line.total == null ? "" : String(line.total)}
                  aria-invalid={errors.total != null}
                  onChange={(e) => onUpdate({ total: e.target.value })}
                />
                {errors.total ? (
                  <p className="text-destructive text-xs" role="alert">
                    {t(errors.total)}
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor={fieldId("reason")}>{t("builder.cart.line.reason")}</Label>
                <Textarea
                  id={fieldId("reason")}
                  rows={2}
                  placeholder={t("builder.cart.line.reason_placeholder")}
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
            <Label htmlFor={fieldId("note")}>{t("builder.cart.line.note")}</Label>
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
