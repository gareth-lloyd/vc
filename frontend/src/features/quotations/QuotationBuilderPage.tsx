import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { useCurrencies } from "@/features/admin/currencies/hooks";
import { useEnquiry } from "@/features/enquiries/hooks";
import { QuoteCriteriaForm } from "./components/QuoteCriteriaForm";
import { QuoteResultsList } from "./components/QuoteResultsList";
import { QuoteCart } from "./components/QuoteCart";
import { SaveQuoteDialog } from "./components/SaveQuoteDialog";
import { SendPreviewDialog } from "./components/SendPreviewDialog";
import { useQuoteOptionsSearch } from "./hooks";
import type { QuotationDetail, QuoteCriteriaInput, QuoteOption, StagedLine } from "./schemas";

// Which commit the operator triggered — Save draft lands on the detail page;
// Send to guest persists first, then opens the send-preview dialog.
type SaveIntent = "draft" | "send";

export function QuotationBuilderPage() {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const enquiryParam = params.get("enquiry");
  const enquiryId = enquiryParam && /^\d+$/.test(enquiryParam) ? Number(enquiryParam) : undefined;

  const enquiryQuery = useEnquiry(enquiryId);
  const enquiry = enquiryQuery.data ?? null;

  // Empty until the tenant's active currencies load — the effect below seeds it
  // from the list rather than a hardcoded guess, so there's no flash of a
  // currency the tenant may not have and the Select never binds an out-of-range
  // value. `formatMoney`/search treat "" as not-yet-priced (renders "—").
  const [currency, setCurrency] = useState("");
  const [staged, setStaged] = useState<StagedLine[]>([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveIntent, setSaveIntent] = useState<SaveIntent>("draft");
  const [sentQuotation, setSentQuotation] = useState<QuotationDetail | null>(null);
  const [lastCriteria, setLastCriteria] = useState<QuoteCriteriaInput | null>(null);

  const search = useQuoteOptionsSearch();
  const currenciesQuery = useCurrencies({});
  const activeCurrencies = useMemo(
    () => (currenciesQuery.data?.results ?? []).filter((c) => c.is_active),
    [currenciesQuery.data],
  );

  // Seed the currency from the tenant's active list as soon as it lands (and
  // re-seed if the current code somehow isn't active). Fires at mount before any
  // search, so there's no cart to clear, and never fights a manual choice — the
  // picker only offers active codes.
  useEffect(() => {
    if (activeCurrencies.length === 0) return;
    if (!activeCurrencies.some((c) => c.code === currency)) {
      setCurrency(activeCurrencies[0].code);
    }
  }, [activeCurrencies, currency]);

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

  // Returns whether the search succeeded so callers (currency change) can
  // decide whether to act on stale state. Errors are caught + toasted here.
  const runSearch = async (values: QuoteCriteriaInput, curr: string): Promise<boolean> => {
    try {
      await search.mutateAsync({ criteria: values, currency: curr });
      return true;
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("builder.errors.search_failed")
          : t("builder.errors.search_failed");
      toast.error(message);
      return false;
    }
  };

  const handleSearch = (values: QuoteCriteriaInput) => {
    setLastCriteria(values);
    void runSearch(values, currency);
  };

  // Currency is a pricing input: the staged lines were priced in the old one,
  // so re-run the last search in the new currency and clear the cart — but only
  // once the new-currency results land. Clearing eagerly would wipe the cart
  // even when the re-search fails (offline, transient 5xx), leaving the operator
  // with nothing and no way back. On failure, revert the picker so cart and
  // currency stay consistent.
  const handleCurrencyChange = async (code: string) => {
    const prev = currency;
    setCurrency(code);
    if (!lastCriteria) return; // nothing searched yet → nothing to lose
    const ok = await runSearch(lastCriteria, code);
    if (ok) setStaged([]);
    else setCurrency(prev);
  };

  const handleAdd = (option: QuoteOption) => {
    if (!lastCriteria) return;
    setStaged((prev) => {
      if (prev.some((line) => line.property_id === option.property_id)) return prev;
      const next: StagedLine = {
        property_id: option.property_id,
        property_name: option.property_name,
        hero_image_url: option.hero_image_url ?? null,
        // Persist the operator's requested stay; the backend shifts a
        // non-conforming arrival to the changeover day on save and records the
        // move (GAP-007), so it stays the single source of the shift.
        date_from: lastCriteria.date_from,
        date_to: lastCriteria.date_to,
        // Display the dates the engine actually priced — possibly shifted
        // forward. The note fires when they differ from the requested dates.
        priced_date_from: option.date_from ?? lastCriteria.date_from,
        priced_date_to: option.date_to ?? lastCriteria.date_to,
        adults: lastCriteria.adults,
        children: lastCriteria.children,
        total: option.total ?? null,
        discount: "0",
        inclusions: "",
        price_override_reason: "",
        is_manual: false,
        notes: "",
      };
      return [...prev, next];
    });
  };

  const handleUpdateLine = (propertyId: number, patch: Partial<StagedLine>) => {
    setStaged((prev) =>
      prev.map((line) => (line.property_id === propertyId ? { ...line, ...patch } : line)),
    );
  };

  const handleRemove = (propertyId: number) => {
    setStaged((prev) => prev.filter((line) => line.property_id !== propertyId));
  };

  const openSave = (intent: SaveIntent) => {
    setSaveIntent(intent);
    setSaveOpen(true);
  };

  const handleSaved = (quotation: QuotationDetail) => {
    if (saveIntent === "send") {
      // Persisted first; now preview + send against the real quotation.
      setSentQuotation(quotation);
    } else {
      navigate(`/quotations/${quotation.id}`);
    }
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

      <div className="grid gap-6 px-6 py-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="min-w-0 space-y-6">
          <section className="space-y-3">
            <h3 className="text-foreground text-base font-semibold">
              {t("builder.criteria.title")}
            </h3>
            <div className="space-y-2">
              <Label htmlFor="qb-currency">{t("builder.criteria.currency")}</Label>
              <Select
                value={currency}
                onValueChange={(code) => void handleCurrencyChange(code)}
                disabled={search.isPending}
              >
                <SelectTrigger id="qb-currency" aria-label={t("builder.criteria.currency")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {activeCurrencies.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.code} — {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">{t("builder.criteria.currency_hint")}</p>
            </div>
            <QuoteCriteriaForm
              initial={initial}
              isSubmitting={search.isPending}
              disabled={!currency}
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
        </div>

        <aside className="lg:sticky lg:top-6 lg:self-start">
          <QuoteCart
            lines={staged}
            currency={currency}
            onUpdateLine={handleUpdateLine}
            onRemove={handleRemove}
            onSaveDraft={() => openSave("draft")}
            onSendToGuest={() => openSave("send")}
          />
        </aside>
      </div>

      <SaveQuoteDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        enquiry={enquiry}
        lines={staged}
        currencyCode={currency}
        onSaved={handleSaved}
      />

      {sentQuotation ? (
        <SendPreviewDialog
          open={sentQuotation != null}
          onOpenChange={(open) => {
            if (!open) {
              // Whether sent or dismissed, the draft is persisted — leave the
              // builder for the saved quotation's detail page.
              const id = sentQuotation.id;
              setSentQuotation(null);
              navigate(`/quotations/${id}`);
            }
          }}
          quotation={sentQuotation}
        />
      ) : null}
    </div>
  );
}
