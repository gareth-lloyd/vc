import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
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
          className="border-border flex items-center justify-between rounded-md border p-3"
        >
          <div>
            <h4 className="text-foreground text-sm font-semibold">{option.property_name}</h4>
            <p className="text-muted-foreground text-xs">
              {t("builder.results.total")}:{" "}
              <span className="text-foreground font-medium">
                {option.total != null ? `${currency} ${option.total}` : "—"}
              </span>
            </p>
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
        <details className="text-sm">
          <summary className="text-muted-foreground cursor-pointer">
            {t("builder.results.unavailable_count", { count: unavailable.length })}
          </summary>
          <ul className="mt-2 space-y-1">
            {unavailable.map((option) => (
              <li
                key={option.property_id}
                className="text-muted-foreground flex justify-between gap-2"
              >
                <span>{option.property_name}</span>
                <span className="text-xs italic">{option.error_detail ?? option.error_code}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
