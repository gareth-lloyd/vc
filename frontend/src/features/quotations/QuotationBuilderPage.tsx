import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { useEnquiry } from "@/features/enquiries/hooks";
import { QuoteCriteriaForm } from "./components/QuoteCriteriaForm";
import { QuoteResultsList } from "./components/QuoteResultsList";
import { QuoteLinesPanel } from "./components/QuoteLinesPanel";
import { SaveQuoteDialog } from "./components/SaveQuoteDialog";
import { useQuoteOptionsSearch } from "./hooks";
import type { QuoteCriteriaInput, QuoteOption, StagedLine } from "./schemas";

const DEFAULT_CURRENCY = "USD";

export function QuotationBuilderPage() {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const enquiryParam = params.get("enquiry");
  const enquiryId = enquiryParam && /^\d+$/.test(enquiryParam) ? Number(enquiryParam) : undefined;

  const enquiryQuery = useEnquiry(enquiryId);
  const enquiry = enquiryQuery.data ?? null;

  const [currency, setCurrency] = useState(DEFAULT_CURRENCY);
  const [staged, setStaged] = useState<StagedLine[]>([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [lastCriteria, setLastCriteria] = useState<QuoteCriteriaInput | null>(null);

  const search = useQuoteOptionsSearch();

  const initial = useMemo<Partial<QuoteCriteriaInput>>(() => {
    if (!enquiry) return {};
    return {
      date_from: enquiry.date_from ?? "",
      date_to: enquiry.date_to ?? "",
      adults: enquiry.adults,
      children: enquiry.children ?? 0,
      min_bedrooms: enquiry.min_bedrooms ?? null,
    };
  }, [enquiry]);

  const stagedPropertyIds = useMemo(
    () => new Set(staged.map((line) => line.property_id)),
    [staged],
  );

  const handleSearch = async (values: QuoteCriteriaInput) => {
    setLastCriteria(values);
    try {
      await search.mutateAsync({ criteria: values, currency });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("builder.errors.search_failed")
          : t("builder.errors.search_failed");
      toast.error(message);
    }
  };

  const handleAdd = (option: QuoteOption) => {
    if (!lastCriteria) return;
    setStaged((prev) => {
      if (prev.some((line) => line.property_id === option.property_id)) return prev;
      const next: StagedLine = {
        property_id: option.property_id,
        property_name: option.property_name,
        date_from: lastCriteria.date_from,
        date_to: lastCriteria.date_to,
        adults: lastCriteria.adults,
        children: lastCriteria.children,
        total: option.total ?? null,
        is_manual: false,
        notes: "",
      };
      return [...prev, next];
    });
  };

  const handleRemove = (propertyId: number) => {
    setStaged((prev) => prev.filter((line) => line.property_id !== propertyId));
  };

  if (enquiryQuery.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (enquiryId == null) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("builder.errors.no_enquiry_title")}
          description={t("builder.errors.no_enquiry_description")}
        />
      </div>
    );
  }

  if (enquiryQuery.isError || !enquiry) {
    const is404 = enquiryQuery.error instanceof ApiError && enquiryQuery.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={
            is404 ? t("builder.errors.enquiry_not_found") : t("builder.errors.enquiry_load_failed")
          }
          description={
            is404
              ? t("builder.errors.enquiry_not_found_description")
              : t("builder.errors.enquiry_load_failed_description")
          }
          onRetry={is404 ? undefined : () => enquiryQuery.refetch()}
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("builder.title")}
        subtitle={t("builder.subtitle", { reference: enquiry.reference })}
        breadcrumbs={[
          { label: t("detail.breadcrumb_root") },
          { label: t("detail.breadcrumb_list"), to: "/quotations" },
          { label: t("builder.breadcrumb_self") },
        ]}
      />

      <TwoColumn
        rightRail={
          <div className="space-y-4">
            <div>
              <h2 className="text-foreground text-lg font-semibold">
                {t("builder.rail.staged_title")}
              </h2>
              <p className="text-muted-foreground text-sm">
                {t("builder.rail.staged_count", { count: staged.length })}
              </p>
            </div>
            <Button
              type="button"
              className="w-full"
              disabled={staged.length === 0}
              onClick={() => setSaveOpen(true)}
            >
              {t("builder.rail.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => navigate(`/enquiries/${enquiry.id}`)}
            >
              {t("builder.rail.back_to_enquiry")}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <section className="space-y-3">
            <h3 className="text-foreground text-base font-semibold">
              {t("builder.criteria.title")}
            </h3>
            <QuoteCriteriaForm
              initial={initial}
              isSubmitting={search.isPending}
              onSubmit={handleSearch}
            />
          </section>

          <section className="space-y-3">
            <h3 className="text-foreground text-base font-semibold">
              {t("builder.results.title")}
            </h3>
            <QuoteResultsList
              options={search.data}
              isLoading={search.isPending}
              currency={currency}
              stagedPropertyIds={stagedPropertyIds}
              onAdd={handleAdd}
            />
          </section>

          <section className="space-y-3">
            <h3 className="text-foreground text-base font-semibold">{t("builder.staged.title")}</h3>
            <QuoteLinesPanel lines={staged} currency={currency} onRemove={handleRemove} />
          </section>
        </div>
      </TwoColumn>

      <SaveQuoteDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        enquiry={enquiry}
        lines={staged}
        currencyCode={currency}
        onCurrencyChange={setCurrency}
        onSaved={(quotation) => navigate(`/quotations/${quotation.id}`)}
      />
    </div>
  );
}
