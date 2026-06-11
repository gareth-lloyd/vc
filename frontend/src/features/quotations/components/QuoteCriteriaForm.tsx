import { useEffect, useMemo } from "react";
import { useController, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addDaysIso } from "@/lib/format/date";
import { quoteCriteriaInputSchema, type QuoteCriteriaInput } from "../schemas";

const MIN_FLEX = 0;
const MAX_FLEX = 3;

interface Props {
  initial: Partial<QuoteCriteriaInput>;
  isSubmitting: boolean;
  onSubmit: (values: QuoteCriteriaInput) => void;
}

const DEFAULTS: QuoteCriteriaInput = {
  date_from: "",
  date_to: "",
  adults: 2,
  children: 0,
  country: "",
  region: "",
  min_bedrooms: null,
  max_bedrooms: null,
  q: "",
  flex_days: 0,
};

export function QuoteCriteriaForm({ initial, isSubmitting, onSubmit }: Props) {
  const { t } = useTranslation("quotations");

  const form = useForm<QuoteCriteriaInput>({
    resolver: zodResolver(quoteCriteriaInputSchema),
    defaultValues: { ...DEFAULTS, ...initial },
  });

  useEffect(() => {
    form.reset({ ...DEFAULTS, ...initial });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  // ± flexibility stepper (mirrors the enquiry form's spread control). The
  // dates stay the client's preferred stay — the backend widens the window.
  const flexCtrl = useController({ control: form.control, name: "flex_days" });
  const flex = flexCtrl.field.value ?? 0;
  const watchedFrom = useWatch({ control: form.control, name: "date_from" }) ?? "";
  const watchedTo = useWatch({ control: form.control, name: "date_to" }) ?? "";
  const window = useMemo(
    () => ({
      from: watchedFrom ? addDaysIso(watchedFrom, -flex) : "",
      to: watchedTo ? addDaysIso(watchedTo, flex) : "",
    }),
    [watchedFrom, watchedTo, flex],
  );

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      className="space-y-4 rounded-md border p-4"
      noValidate
      aria-label={t("builder.criteria.aria_label")}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="qcf-date-from">{t("builder.criteria.date_from")}</Label>
          <Input
            id="qcf-date-from"
            type="date"
            {...form.register("date_from")}
            aria-invalid={!!form.formState.errors.date_from}
          />
          {form.formState.errors.date_from ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.date_from.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="qcf-date-to">{t("builder.criteria.date_to")}</Label>
          <Input
            id="qcf-date-to"
            type="date"
            {...form.register("date_to")}
            aria-invalid={!!form.formState.errors.date_to}
          />
          {form.formState.errors.date_to ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.date_to.message}
            </p>
          ) : null}
        </div>
      </div>

      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">{t("builder.criteria.flex.label")}</span>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label={t("builder.criteria.flex.decrease_aria")}
              disabled={flex <= MIN_FLEX}
              onClick={() => flexCtrl.field.onChange(Math.max(MIN_FLEX, flex - 1))}
            >
              <Minus className="h-3 w-3" />
            </Button>
            <span className="min-w-[4.5rem] text-center text-sm tabular-nums" aria-live="polite">
              {t("builder.criteria.flex.value", { count: flex })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label={t("builder.criteria.flex.increase_aria")}
              disabled={flex >= MAX_FLEX}
              onClick={() => flexCtrl.field.onChange(Math.min(MAX_FLEX, flex + 1))}
            >
              <Plus className="h-3 w-3" />
            </Button>
          </div>
        </div>
        {window.from && window.to && flex > 0 ? (
          <p className="text-muted-foreground text-xs">
            {t("builder.criteria.flex.window_hint", { from: window.from, to: window.to })}
          </p>
        ) : null}
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
