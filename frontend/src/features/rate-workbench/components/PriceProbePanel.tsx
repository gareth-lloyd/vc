import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import type { Extra } from "@/features/properties/schemas";
import { usePriceProbe } from "../hooks";
import { QuoteResultCard } from "./QuoteResultCard";

interface PriceProbePanelProps {
  propertyId: number;
  /** Opt-in (non-mandatory) extras the guest can toggle into the quote. */
  extras: Extra[];
  /** cardId → "Season · Card" label, to name the winning card in the result. */
  cardLabels: Record<number, string>;
}

/**
 * A read-only "what would a guest pay?" probe. Pick dates + party (+ optional
 * extras/code), hit the pricing engine, and render the guest-side breakdown.
 * `party` is `adults + children` (the engine's single occupancy input); owner
 * economics stay hidden (see QuoteResultCard / BUG-009).
 */
export function PriceProbePanel({ propertyId, extras, cardLabels }: PriceProbePanelProps) {
  const { t } = useTranslation("properties");
  const probe = usePriceProbe();

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  // Party counts are held as raw strings so the fields can be cleared while
  // typing; they're clamped to valid integers only at submit.
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [discountCode, setDiscountCode] = useState("");
  const [optIn, setOptIn] = useState<Set<number>>(new Set());

  const optInExtras = extras.filter((e) => !e.is_mandatory && e.is_active !== false);
  const adultsNum = Math.floor(Number(adults));
  const childrenNum = Math.floor(Number(children));
  const canSubmit = !!dateFrom && !!dateTo && adultsNum >= 1 && !probe.isPending;

  const toggleExtra = (id: number, on: boolean) =>
    setOptIn((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const handleSubmit = () => {
    probe.mutate({
      property_id: propertyId,
      date_from: dateFrom,
      date_to: dateTo,
      adults: Math.max(1, adultsNum || 1),
      children: Math.max(0, childrenNum || 0),
      opt_in_extras: [...optIn],
      discount_code: discountCode.trim(),
    });
  };

  const errorMessage = (() => {
    if (!probe.isError) return null;
    const err = probe.error;
    if (err instanceof ApiError) {
      return err.code === "no_rate_available" ? t("rate_workbench.probe.no_rate") : err.detail;
    }
    return t("rate_workbench.probe.failed");
  })();

  return (
    <section className="border-border space-y-4 border-t pt-6">
      <h2 className="text-foreground text-lg font-semibold">{t("rate_workbench.probe.title")}</h2>
      <p className="text-muted-foreground text-sm">{t("rate_workbench.probe.subtitle")}</p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="probe-from">{t("rate_workbench.probe.date_from")}</Label>
          <Input
            id="probe-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="probe-to">{t("rate_workbench.probe.date_to")}</Label>
          <Input
            id="probe-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="probe-adults">{t("rate_workbench.probe.adults")}</Label>
          <Input
            id="probe-adults"
            type="number"
            min={1}
            value={adults}
            onChange={(e) => setAdults(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="probe-children">{t("rate_workbench.probe.children")}</Label>
          <Input
            id="probe-children"
            type="number"
            min={0}
            value={children}
            onChange={(e) => setChildren(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="probe-code">{t("rate_workbench.probe.discount_code")}</Label>
        <Input
          id="probe-code"
          value={discountCode}
          onChange={(e) => setDiscountCode(e.target.value)}
          className="sm:max-w-xs"
        />
      </div>

      {optInExtras.length > 0 ? (
        <fieldset className="space-y-2">
          <legend className="text-muted-foreground text-xs font-medium">
            {t("rate_workbench.probe.opt_in_extras")}
          </legend>
          <div className="flex flex-wrap gap-4">
            {optInExtras.map((e) => (
              <label key={e.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={optIn.has(e.id)}
                  onCheckedChange={(v) => toggleExtra(e.id, v === true)}
                />
                {e.name}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      <Button onClick={handleSubmit} disabled={!canSubmit}>
        {probe.isPending ? t("rate_workbench.probe.getting") : t("rate_workbench.probe.get_quote")}
      </Button>

      {errorMessage ? (
        <p
          role="status"
          className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-sm"
        >
          {errorMessage}
        </p>
      ) : null}

      {probe.isSuccess && !probe.isPending ? (
        <QuoteResultCard
          quote={probe.data}
          cardLabel={
            probe.data.winning_card_id != null ? cardLabels[probe.data.winning_card_id] : null
          }
        />
      ) : null}
    </section>
  );
}
