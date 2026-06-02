import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMoney } from "@/lib/format/money";
import { PropertyThumbnail } from "./PropertyThumbnail";
import type { QuoteOption } from "../schemas";

interface Props {
  options: QuoteOption[] | undefined;
  isLoading: boolean;
  currency: string;
  stagedPropertyIds: Set<number>;
  onAdd: (option: QuoteOption) => void;
}

export function QuoteResultsList({
  options,
  isLoading,
  currency,
  stagedPropertyIds,
  onAdd,
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
      <EmptyState
        title={t("builder.results.empty.title")}
        description={t("builder.results.empty.description")}
      />
    );
  }

  const available = options.filter((o) => o.available);
  const unavailable = options.filter((o) => !o.available);

  return (
    <div className="space-y-3">
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

      {unavailable.map((option) => (
        <Tooltip key={option.property_id}>
          <TooltipTrigger asChild>
            <article
              className="border-border flex items-center justify-between gap-3 rounded-md border border-dashed p-3 opacity-60"
              aria-label={t("builder.results.unavailable_aria", { name: option.property_name })}
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
  );
}
