import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FactList, FactRow } from "@/components/data/FactList";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import {
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertySeasons,
  useSeasonDetail,
} from "../hooks";
import type { Discount, Extra, PropertyDetail, RateCard, RatePlan } from "../schemas";

interface PricingContext {
  property: PropertyDetail;
}

function ActiveBadge({ isActive }: { isActive: boolean | undefined }) {
  return isActive ? (
    <Badge variant="secondary">Active</Badge>
  ) : (
    <Badge variant="outline">Inactive</Badge>
  );
}

function SeasonsList({
  seasons,
  onSelect,
}: {
  seasons: RatePlan[];
  onSelect: (seasonId: number) => void;
}) {
  if (seasons.length === 0) {
    return <EmptyState title="No seasons defined" />;
  }
  return (
    <ul className="border-border bg-card divide-border divide-y rounded-lg border">
      {seasons.map((plan) => (
        <li key={plan.id}>
          <button
            type="button"
            onClick={() => onSelect(plan.id)}
            className="hover:bg-accent flex w-full items-center justify-between px-4 py-3 text-left text-sm"
          >
            <span className="flex flex-col">
              <span className="text-foreground font-medium">{plan.name}</span>
              <span className="text-muted-foreground text-xs">
                {formatDate(plan.effective_from)} – {formatDate(plan.effective_to)}
                {plan.currency ? ` · ${plan.currency}` : ""}
              </span>
            </span>
            <ActiveBadge isActive={plan.is_active} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function RateCardBlock({ card }: { card: RateCard }) {
  return (
    <div className="border-border bg-card space-y-3 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h4 className="text-foreground text-sm font-semibold">{card.name}</h4>
          {card.description ? (
            <p className="text-muted-foreground text-xs">{card.description}</p>
          ) : null}
          <p className="text-muted-foreground mt-1 text-xs">
            {card.min_nights != null || card.max_nights != null
              ? `Nights ${card.min_nights ?? "?"}–${card.max_nights ?? "?"}`
              : "Any length"}
            {card.changeover_weekday != null
              ? ` · Changeover: weekday ${card.changeover_weekday}`
              : ""}
          </p>
        </div>
        <ActiveBadge isActive={card.is_active} />
      </div>
      {card.rules.length === 0 ? (
        <p className="text-muted-foreground text-xs italic">No rules</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-muted-foreground text-left">
            <tr>
              <th className="py-1 pr-2 font-medium">Dates</th>
              <th className="py-1 pr-2 font-medium">Party</th>
              <th className="py-1 pr-2 font-medium">Nightly</th>
              <th className="py-1 font-medium">Weekly</th>
            </tr>
          </thead>
          <tbody>
            {card.rules.map((rule) => (
              <tr key={rule.id} className="border-border border-t">
                <td className="py-1 pr-2">
                  {formatDate(rule.date_from)} – {formatDate(rule.date_to)}
                </td>
                <td className="py-1 pr-2">
                  {rule.min_party ?? "?"}–{rule.max_party ?? "?"}
                </td>
                <td className="py-1 pr-2">{rule.is_poa ? "POA" : (rule.nightly ?? "—")}</td>
                <td className="py-1">{rule.is_poa ? "POA" : (rule.weekly ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SeasonDetailPanel({ seasonId, onBack }: { seasonId: number; onBack: () => void }) {
  const detail = useSeasonDetail(seasonId);
  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}>
        ← Back to seasons
      </Button>
      {detail.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : detail.isError || !detail.data ? (
        <ErrorState
          title="Couldn't load season"
          description="Try again."
          onRetry={() => detail.refetch()}
        />
      ) : (
        <>
          <FactList>
            <FactRow label="Name" value={detail.data.name} />
            <FactRow label="Currency" value={detail.data.currency ?? "—"} />
            <FactRow label="Price basis" value={detail.data.price_basis ?? "—"} />
            <FactRow
              label="Effective"
              value={`${formatDate(detail.data.effective_from)} – ${formatDate(detail.data.effective_to)}`}
            />
            <FactRow label="Status" value={<ActiveBadge isActive={detail.data.is_active} />} />
          </FactList>
          <div className="space-y-3">
            <h3 className="text-foreground text-sm font-semibold">Rate cards</h3>
            {detail.data.cards.length === 0 ? (
              <EmptyState title="No rate cards" />
            ) : (
              detail.data.cards.map((card) => <RateCardBlock key={card.id} card={card} />)
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ExtrasTable({ extras }: { extras: Extra[] }) {
  if (extras.length === 0) {
    return <EmptyState title="No extras" />;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground text-left text-xs">
        <tr>
          <th className="py-2 pr-2 font-medium">Name</th>
          <th className="py-2 pr-2 font-medium">Kind</th>
          <th className="py-2 pr-2 font-medium">Amount</th>
          <th className="py-2 font-medium">Mandatory</th>
        </tr>
      </thead>
      <tbody>
        {extras.map((extra) => (
          <tr key={extra.id} className="border-border border-t">
            <td className="py-2 pr-2">{extra.name}</td>
            <td className="text-muted-foreground py-2 pr-2">{extra.kind ?? "—"}</td>
            <td className="py-2 pr-2">{formatMoney(extra.amount, extra.currency ?? null)}</td>
            <td className="py-2">{extra.is_mandatory ? "Yes" : "No"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DiscountsTable({ discounts }: { discounts: Discount[] }) {
  if (discounts.length === 0) {
    return <EmptyState title="No discounts" />;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground text-left text-xs">
        <tr>
          <th className="py-2 pr-2 font-medium">Name</th>
          <th className="py-2 pr-2 font-medium">Code</th>
          <th className="py-2 pr-2 font-medium">Kind</th>
          <th className="py-2 pr-2 font-medium">Amount</th>
          <th className="py-2 font-medium">Valid</th>
        </tr>
      </thead>
      <tbody>
        {discounts.map((d) => (
          <tr key={d.id} className="border-border border-t">
            <td className="py-2 pr-2">{d.name}</td>
            <td className="text-muted-foreground py-2 pr-2 font-mono text-xs">{d.code ?? "—"}</td>
            <td className="text-muted-foreground py-2 pr-2">{d.kind ?? "—"}</td>
            <td className="py-2 pr-2">{d.amount ?? "—"}</td>
            <td className="text-muted-foreground py-2">
              {formatDate(d.valid_from)} – {formatDate(d.valid_to)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PricingTab() {
  const { property } = useOutletContext<PricingContext>();
  const propertyKey = property.slug || property.id;
  const seasons = usePropertySeasons(propertyKey);
  const extras = usePropertyExtras(propertyKey);
  const discounts = usePropertyDiscounts(propertyKey);
  const [selectedSeasonId, setSelectedSeasonId] = useState<number | null>(null);

  return (
    <div className="space-y-8 p-6">
      <Section title="Seasons">
        {seasons.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : seasons.isError ? (
          <ErrorState
            title="Couldn't load seasons"
            description="Try again."
            onRetry={() => seasons.refetch()}
          />
        ) : selectedSeasonId != null ? (
          <SeasonDetailPanel seasonId={selectedSeasonId} onBack={() => setSelectedSeasonId(null)} />
        ) : (
          <SeasonsList seasons={seasons.data?.results ?? []} onSelect={setSelectedSeasonId} />
        )}
      </Section>

      <Section title="Extras">
        {extras.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : extras.isError ? (
          <ErrorState
            title="Couldn't load extras"
            description="Try again."
            onRetry={() => extras.refetch()}
          />
        ) : (
          <ExtrasTable extras={extras.data?.results ?? []} />
        )}
      </Section>

      <Section title="Discounts">
        {discounts.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : discounts.isError ? (
          <ErrorState
            title="Couldn't load discounts"
            description="Try again."
            onRetry={() => discounts.refetch()}
          />
        ) : (
          <DiscountsTable discounts={discounts.data?.results ?? []} />
        )}
      </Section>
    </div>
  );
}
