import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/errors";
import { useCurrencies } from "@/features/admin/currencies/hooks";
import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { QuoteCriteriaForm } from "./QuoteCriteriaForm";
import { QuoteResultsList } from "./QuoteResultsList";
import { QuoteCart } from "./QuoteCart";
import { SaveQuoteDialog } from "./SaveQuoteDialog";
import { SendPreviewDialog } from "./SendPreviewDialog";
import { useQuoteOptionsSearch } from "../hooks";
import type {
  HiddenCapacityProperty,
  QuotationDetail,
  QuoteCriteriaInput,
  QuoteOption,
  StagedLine,
} from "../schemas";

// Which commit the operator triggered — Save draft persists and completes;
// Send to guest persists first, then opens the send-preview dialog.
type SaveIntent = "draft" | "send";

// Keep the first occurrence per property when appending a loaded page — a
// belt-and-braces guard against the backend ever returning an overlapping row
// across page boundaries.
function dedupeById(options: QuoteOption[]): QuoteOption[] {
  const seen = new Set<number>();
  return options.filter((o) => (seen.has(o.property_id) ? false : seen.add(o.property_id)));
}

interface QuoteBuilderProps {
  enquiry: EnquiryDetail;
  // Fired once a quotation is committed — after a draft saves, or after the
  // send-preview dialog is dismissed (the draft is persisted either way). The
  // inline workspace passes a handler that closes the builder and stays put
  // (the quote-stack refreshes in place via the enquiry-detail cache
  // invalidation SaveQuoteDialog fires).
  onComplete?: (quotation: QuotationDetail) => void;
}

export function QuoteBuilder({ enquiry, onComplete }: QuoteBuilderProps) {
  const { t } = useTranslation("quotations");

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

  // Accumulated priced options across loaded candidate pages. `undefined` is the
  // idle state (no search run yet); `[]` means searched-but-empty. The results
  // come from the search mutation but live here so Load-more can append rather
  // than replace (the mutation's own `data` is replaced on every call).
  const [results, setResults] = useState<QuoteOption[] | undefined>(undefined);
  // Capacity-unset properties that matched the name search but couldn't be
  // priced — a hint, computed once per fresh search (not per page).
  const [hiddenForCapacity, setHiddenForCapacity] = useState<HiddenCapacityProperty[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [totalMatched, setTotalMatched] = useState(0);
  const [searchPage, setSearchPage] = useState(1);
  // Distinguishes the Load-more spinner from the full-results skeleton — both
  // ride the same mutation's `isPending`.
  const [isLoadingMore, setIsLoadingMore] = useState(false);

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

  const initial = useMemo<Partial<QuoteCriteriaInput>>(
    () => ({
      date_from: enquiry.date_from ?? "",
      date_to: enquiry.date_to ?? "",
      adults: enquiry.adults,
      children: enquiry.children ?? 0,
      min_bedrooms: enquiry.min_bedrooms ?? null,
    }),
    [enquiry],
  );

  const stagedPropertyIds = useMemo(
    () => new Set(staged.map((line) => line.property_id)),
    [staged],
  );

  // Runs one page of the search. Page 1 replaces the results; page 2+ (Load
  // more) concatenates. Returns whether it succeeded so callers (currency
  // change) can decide whether to act on stale state. Errors are caught +
  // toasted here; on failure existing results are left untouched so the
  // Load-more button stays. `lastCriteria` is recorded only on success, so a
  // failed re-search can't pair stale prices with the new form criteria.
  const runSearch = async (
    values: QuoteCriteriaInput,
    curr: string,
    page: number,
  ): Promise<boolean> => {
    const append = page > 1;
    try {
      const result = await search.mutateAsync({ criteria: values, currency: curr, page });
      setResults((prev) =>
        append && prev ? dedupeById([...prev, ...result.options]) : result.options,
      );
      setHasMore(result.hasMore);
      setTotalMatched(result.totalMatched);
      setSearchPage(page);
      setLastCriteria(values);
      // The capacity hint describes the whole search; the API only computes it
      // on page 1, so refresh it on a fresh search and keep it across Load-more.
      if (!append) setHiddenForCapacity(result.hiddenForCapacity);
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
    void runSearch(values, currency, 1);
  };

  const handleLoadMore = async () => {
    // Guard re-entrancy: the button disables on `isLoadingMore`, but only after
    // a re-render — a fast double-click would otherwise fire the same page twice.
    if (!lastCriteria || isLoadingMore || search.isPending) return;
    setIsLoadingMore(true);
    try {
      await runSearch(lastCriteria, currency, searchPage + 1);
    } finally {
      setIsLoadingMore(false);
    }
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
    const ok = await runSearch(lastCriteria, code, 1);
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
      onComplete?.(quotation);
    }
  };

  return (
    <>
      <div className="space-y-6">
        <section className="space-y-3">
          <h3 className="text-foreground text-base font-semibold">{t("builder.criteria.title")}</h3>
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
          <h3 className="text-foreground text-base font-semibold">{t("builder.results.title")}</h3>
          <QuoteResultsList
            options={results}
            hiddenForCapacity={hiddenForCapacity}
            isLoading={search.isPending && !isLoadingMore}
            currency={currency}
            stagedPropertyIds={stagedPropertyIds}
            onAdd={handleAdd}
            hasMore={hasMore}
            isLoadingMore={isLoadingMore}
            totalMatched={totalMatched}
            onLoadMore={() => void handleLoadMore()}
          />
        </section>

        {/* Cart sits at the foot as a full-width block in normal flow. The
            builder is plain vertical flow (criteria → results → cart) and lets
            its host own the column layout, so it reads the same scrolled
            top-to-bottom whatever pane it's mounted in — ending on Save draft /
            Send to guest. */}
        <QuoteCart
          lines={staged}
          currency={currency}
          onUpdateLine={handleUpdateLine}
          onRemove={handleRemove}
          onSaveDraft={() => openSave("draft")}
          onSendToGuest={() => openSave("send")}
        />
      </div>

      {/* Mount only while open so the dialog's currencies + current-terms
          queries fire on the save action, not on every builder render — the
          inline builder is expanded by default on a quote-less enquiry. */}
      {saveOpen ? (
        <SaveQuoteDialog
          open
          onOpenChange={setSaveOpen}
          enquiry={enquiry}
          lines={staged}
          currencyCode={currency}
          onSaved={handleSaved}
        />
      ) : null}

      {sentQuotation ? (
        <SendPreviewDialog
          open={sentQuotation != null}
          onOpenChange={(open) => {
            if (!open) {
              // Whether sent or dismissed, the draft is persisted — hand the
              // saved quotation back to the host to decide what happens next.
              const quotation = sentQuotation;
              setSentQuotation(null);
              onComplete?.(quotation);
            }
          }}
          quotation={sentQuotation}
        />
      ) : null}
    </>
  );
}
