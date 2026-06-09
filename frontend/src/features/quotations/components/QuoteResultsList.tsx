import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMoney } from "@/lib/format/money";
import { PropertyThumbnail } from "./PropertyThumbnail";
import type { HiddenCapacityProperty, QuoteOption } from "../schemas";

interface Props {
  options: QuoteOption[] | undefined;
  isLoading: boolean;
  currency: string;
  stagedPropertyIds: Set<number>;
  onAdd: (option: QuoteOption) => void;
  hiddenForCapacity?: HiddenCapacityProperty[];
}

function CapacityHint({ properties }: { properties: HiddenCapacityProperty[] }) {
  const { t } = useTranslation("quotations");
  if (properties.length === 0) return null;
  return (
    <div
      className="border-border bg-muted/40 space-y-2 rounded-md border border-dashed p-3"
      role="status"
    >
      <p className="text-muted-foreground text-xs">{t("builder.results.capacity_hint.intro")}</p>
      <ul className="space-y-1">
        {properties.map((p) => (
          <li key={p.id} className="text-sm">
            <Link to={`/properties/${p.slug ?? p.id}/details`} className="font-medium underline">
              {p.name}
            </Link>{" "}
            <span className="text-muted-foreground">
              {t("builder.results.capacity_hint.suffix")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function QuoteResultsList({
  options,
  isLoading,
  currency,
  stagedPropertyIds,
  onAdd,
  hiddenForCapacity = [],
}: Props) {
  const { t } = useTranslation("quotations");

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (options == null) {
    return (
      <EmptyState
        title={t("builder.results.idle.title")}
        description={t("builder.results.idle.description")}
      />
    );
  }

  if (options.length === 0) {
    return (
      <div className="space-y-3">
        <EmptyState
          title={t("builder.results.empty.title")}
          description={t("builder.results.empty.description")}
        />
        <CapacityHint properties={hiddenForCapacity} />
      </div>
    );
  }

  const available = options.filter((o) => o.available);
  const unavailable = options.filter((o) => !o.available);

  return (
    <div className="space-y-3">
      <CapacityHint properties={hiddenForCapacity} />
      {available.map((option) => (
        <article
          key={option.property_id}
          className="border-border flex items-center justify-between gap-3 rounded-md border p-3"
        >
          <div className="flex items-center gap-3">
            <PropertyThumbnail
              src={option.hero_image_url}
              fallbackText={option.property_name}
              alt={t("builder.results.thumbnail_alt", { name: option.property_name })}
            />
            <div>
              <h4 className="text-foreground text-sm font-semibold">{option.property_name}</h4>
              <p className="text-muted-foreground text-xs">
                {t("builder.results.total")}:{" "}
                <span className="text-foreground font-medium">
                  {formatMoney(option.total ?? null, currency)}
                </span>
              </p>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant={stagedPropertyIds.has(option.property_id) ? "secondary" : "default"}
            disabled={stagedPropertyIds.has(option.property_id)}
            onClick={() => onAdd(option)}
          >
            {stagedPropertyIds.has(option.property_id)
              ? t("builder.results.added")
              : t("builder.results.add")}
          </Button>
        </article>
      ))}

      {unavailable.length > 0 ? (
        <Collapsible
          className="border-border rounded-md border border-dashed"
          headerClassName="text-muted-foreground hover:text-foreground gap-2 p-3 text-sm"
          title={t("builder.results.unavailable_count", { count: unavailable.length })}
        >
          <div className="space-y-3 p-3 pt-0">
            {unavailable.map((option) => (
              <Tooltip key={option.property_id}>
                <TooltipTrigger asChild>
                  <article
                    className="border-border flex items-center justify-between gap-3 rounded-md border border-dashed p-3 opacity-60"
                    aria-label={t("builder.results.unavailable_aria", {
                      name: option.property_name,
                    })}
                  >
                    <div className="flex items-center gap-3">
                      <PropertyThumbnail
                        src={option.hero_image_url}
                        fallbackText={option.property_name}
                        alt={t("builder.results.thumbnail_alt", { name: option.property_name })}
                      />
                      <div>
                        <h4 className="text-foreground text-sm font-semibold">
                          {option.property_name}
                        </h4>
                        <p className="text-muted-foreground text-xs">
                          {t("builder.results.unavailable")}
                        </p>
                      </div>
                    </div>
                  </article>
                </TooltipTrigger>
                <TooltipContent>
                  {option.error_detail ?? option.error_code ?? t("builder.results.unavailable")}
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </Collapsible>
      ) : null}
    </div>
  );
}
