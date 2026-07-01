import { useEffect } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type QuoteCriteriaInput, type QuoteSearchForm, quoteSearchFormSchema } from "../schemas";
import { searchFormToCriteria } from "../searchCriteria";

interface Props {
  initial: Partial<QuoteSearchForm>;
  isSubmitting: boolean;
  // Receives the translated WIRE criteria — the arrival-window form shape
  // (GAP-043) stays internal to this component.
  onSubmit: (values: QuoteCriteriaInput) => void;
}

// Stepper ceiling — quotes beyond three months out of a single search are not
// a real operator flow, and an unbounded + button invites runaway values.
const MAX_WEEKS = 12;

const DEFAULTS: QuoteSearchForm = {
  arrive_from: "",
  arrive_to: "",
  weeks: 1,
  specific_date: false,
  adults: 2,
  children: 0,
  country: "",
  region: "",
  min_bedrooms: null,
  max_bedrooms: null,
  q: "",
};

export function QuoteCriteriaForm({ initial, isSubmitting, onSubmit }: Props) {
  const { t } = useTranslation("quotations");

  const form = useForm<QuoteSearchForm>({
    resolver: zodResolver(quoteSearchFormSchema),
    defaultValues: { ...DEFAULTS, ...initial },
  });

  useEffect(() => {
    form.reset({ ...DEFAULTS, ...initial });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  // The preferred stay length in whole weeks. The engine snaps each offered
  // block to the winning card's min/max nights, so the per-cell nights in the
  // results stay authoritative — this is a preference, not a guarantee.
  const weeksCtrl = useController({ control: form.control, name: "weeks" });
  const weeks = weeksCtrl.field.value ?? 1;

  // Legacy IsSpecificDate: collapses the arrival window to the exact
  // arrive_from (the translator sends flex 0).
  const specificCtrl = useController({ control: form.control, name: "specific_date" });
  const specificDate = specificCtrl.field.value ?? false;

  return (
    <form
      onSubmit={form.handleSubmit((values) => onSubmit(searchFormToCriteria(values)))}
      className="space-y-4 rounded-md border p-4"
      noValidate
      aria-label={t("builder.criteria.aria_label")}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className={specificDate ? "col-span-2 space-y-2" : "space-y-2"}>
          <Label htmlFor="qcf-arrive-from">{t("builder.criteria.arrive_from")}</Label>
          <Input
            id="qcf-arrive-from"
            type="date"
            {...form.register("arrive_from")}
            aria-invalid={!!form.formState.errors.arrive_from}
          />
          {form.formState.errors.arrive_from ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.arrive_from.message}
            </p>
          ) : null}
        </div>
        {specificDate ? null : (
          <div className="space-y-2">
            <Label htmlFor="qcf-arrive-to">{t("builder.criteria.arrive_to")}</Label>
            <Input
              id="qcf-arrive-to"
              type="date"
              {...form.register("arrive_to")}
              aria-invalid={!!form.formState.errors.arrive_to}
            />
            {form.formState.errors.arrive_to ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.arrive_to.message}
              </p>
            ) : null}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">{t("builder.criteria.weeks.label")}</span>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label={t("builder.criteria.weeks.decrease_aria")}
              disabled={weeks <= 1}
              onClick={() => weeksCtrl.field.onChange(Math.max(1, weeks - 1))}
            >
              <Minus className="h-3 w-3" />
            </Button>
            <span className="min-w-[4.5rem] text-center text-sm tabular-nums" aria-live="polite">
              {t("builder.criteria.weeks.value", { count: weeks })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label={t("builder.criteria.weeks.increase_aria")}
              disabled={weeks >= MAX_WEEKS}
              onClick={() => weeksCtrl.field.onChange(Math.min(MAX_WEEKS, weeks + 1))}
            >
              <Plus className="h-3 w-3" />
            </Button>
          </div>
        </div>
        <CheckboxLabel>
          <Checkbox
            checked={specificDate}
            onCheckedChange={(v) => specificCtrl.field.onChange(v === true)}
            aria-label={t("builder.criteria.specific_date")}
          />
          {t("builder.criteria.specific_date")}
        </CheckboxLabel>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="qcf-adults">{t("builder.criteria.adults")}</Label>
          <Input
            id="qcf-adults"
            type="number"
            min={1}
            {...form.register("adults", { valueAsNumber: true })}
            aria-invalid={!!form.formState.errors.adults}
          />
          {form.formState.errors.adults ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.adults.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="qcf-children">{t("builder.criteria.children")}</Label>
          <Input
            id="qcf-children"
            type="number"
            min={0}
            {...form.register("children", { valueAsNumber: true })}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="qcf-country">{t("builder.criteria.country")}</Label>
          <Input
            id="qcf-country"
            placeholder={t("builder.criteria.country_placeholder")}
            {...form.register("country")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="qcf-region">{t("builder.criteria.region")}</Label>
          <Input
            id="qcf-region"
            placeholder={t("builder.criteria.region_placeholder")}
            {...form.register("region")}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label htmlFor="qcf-min-bedrooms">{t("builder.criteria.min_bedrooms")}</Label>
          <Input
            id="qcf-min-bedrooms"
            type="number"
            min={0}
            {...form.register("min_bedrooms", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="qcf-max-bedrooms">{t("builder.criteria.max_bedrooms")}</Label>
          <Input
            id="qcf-max-bedrooms"
            type="number"
            min={0}
            {...form.register("max_bedrooms", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="qcf-q">{t("builder.criteria.q")}</Label>
          <Input
            id="qcf-q"
            placeholder={t("builder.criteria.q_placeholder")}
            {...form.register("q")}
          />
        </div>
      </div>

      <div className="flex justify-end">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? t("builder.criteria.searching") : t("builder.criteria.search")}
        </Button>
      </div>
    </form>
  );
}
