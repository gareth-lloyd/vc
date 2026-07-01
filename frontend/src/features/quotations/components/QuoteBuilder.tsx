import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/errors";
import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { EnquirySummaryHeader } from "./EnquirySummaryHeader";
import { QuoteCriteriaForm } from "./QuoteCriteriaForm";
import { QuoteResultsList } from "./QuoteResultsList";
import { QuoteShortlist } from "./QuoteShortlist";
import { SaveQuoteDialog } from "./SaveQuoteDialog";
import { SendPreviewDialog } from "./SendPreviewDialog";
import { useQuoteOptionsSearch } from "../hooks";
import { enquiryToSearchForm } from "../searchCriteria";
import { nightsCount } from "@/lib/nights";
import {
  type ChosenStay,
  type HiddenCapacityProperty,
  type OccupancyBand,
  type QuotationDetail,
  type QuoteCriteriaInput,
  type QuoteOption,
  type QuoteSearchForm,
  type StagedBand,
  type StagedLine,
  stagedLineId,
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

  // Seed the arrival-window form from the enquiry (GAP-043): its dates ±
  // flexibility_days become the window, its stay length rounds to weeks.
  const initial = useMemo<Partial<QuoteSearchForm>>(() => enquiryToSearchForm(enquiry), [enquiry]);

  // The staged line_ids (`${property_id}:${date_from}`) — the results side
  // derives both per-property and (from U4) per-week staged markers from this.
  const stagedKeys = useMemo(() => new Set(staged.map((line) => line.line_id)), [staged]);

  // Runs one page of the search. Page 1 replaces the results; page 2+ (Load
  // more) concatenates. No currency input (GAP-014): each villa is priced in
  // its own rate plan's currency. Errors are caught + toasted here; on failure
  // existing results are left untouched so the Load-more button stays.
  // `lastCriteria` is recorded only on success, so a failed re-search can't
  // pair stale prices with the new form criteria.
  const runSearch = async (values: QuoteCriteriaInput, page: number): Promise<boolean> => {
    const append = page > 1;
    try {
      const result = await search.mutateAsync({ criteria: values, page });
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
    void runSearch(values, 1);
  };

  const handleLoadMore = async () => {
    // Guard re-entrancy: the button disables on `isLoadingMore`, but only after
    // a re-render — a fast double-click would otherwise fire the same page twice.
    if (!lastCriteria || isLoadingMore || search.isPending) return;
    setIsLoadingMore(true);
    try {
      await runSearch(lastCriteria, searchPage + 1);
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleAdd = (option: QuoteOption, stay?: ChosenStay, selectedBands?: OccupancyBand[]) => {
    if (!lastCriteria) return;
    // GAP-044: a banded result hands over the CHECKED occupancy brackets. They
    // stage onto the line as alternatives — no single total (bands never sum),
    // never manual; each expands to its own saved line at save time.
    const bands: StagedBand[] | undefined =
      selectedBands && selectedBands.length > 0
        ? selectedBands.map((b) => ({
            min_party: b.min_party,
            max_party: b.max_party,
            adults: b.adults,
            total: b.total ?? null,
            currency: b.currency_code ?? null,
            is_poa: b.is_poa ?? false,
            checked: true,
          }))
        : undefined;
    // The chosen stay's dates become the line's requested dates when the stay
    // is a real alternative: an explicitly picked non-default block, or a
    // default block the search rounded to a different length than requested.
    // A default block with the SAME night count is the preferred stay
    // (possibly changeover-shifted): keep posting the criteria dates so the
    // backend stays the single source of the shift (GAP-007) and records it.
    const useStayDates =
      stay != null &&
      (!stay.is_default ||
        nightsCount(stay.date_from, stay.date_to) !==
          nightsCount(lastCriteria.date_from, lastCriteria.date_to));
    const dateFrom = useStayDates ? stay.date_from : lastCriteria.date_from;
    const dateTo = useStayDates ? stay.date_to : lastCriteria.date_to;
    const lineId = stagedLineId(option.property_id, dateFrom);
    setStaged((prev) => {
      if (prev.some((line) => line.line_id === lineId)) return prev;
      // Q-013: a no-rate villa stages straight onto the manual path — there is
      // no engine price, so the operator must type the total (legacy NO RATE).
      const manualOnly = option.error_code === "no_rate_available";
      const next: StagedLine = {
        line_id: lineId,
        property_id: option.property_id,
        property_name: option.property_name,
        hero_image_url: option.hero_image_url ?? null,
        date_from: dateFrom,
        date_to: dateTo,
        // Display the dates the engine actually priced — possibly shifted
        // forward. The note fires when they differ from the requested dates.
        priced_date_from: stay?.priced_date_from ?? option.date_from ?? dateFrom,
        priced_date_to: stay?.priced_date_to ?? option.date_to ?? dateTo,
        adults: lastCriteria.adults,
        children: lastCriteria.children,
        // The currency the engine priced this option in — carried per line
        // (GAP-014) so the shortlist and save path stay per-currency. A banded
        // line takes its currency from the first band and has NO single total.
        currency: bands
          ? (bands[0].currency ?? null)
          : stay
            ? stay.currency
            : (option.currency ?? null),
        total: bands ? null : stay ? stay.total : (option.total ?? null),
        discount: "0",
        // Seed from the winning plan's inclusion text (legacy parity —
        // ResService.cs:1241). Display-only convenience pre-save: the backend
        // seeds authoritatively at line creation; still editable in the shortlist.
        inclusions: stay?.inclusion ?? option.inclusion ?? "",
        price_override_reason: "",
        // A banded line is never manual — each band is priced by the server.
        is_manual: bands ? false : manualOnly,
        manual_only: bands ? false : manualOnly,
        notes: "",
        ...(bands ? { occupancy_bands: bands } : {}),
      };
      return [...prev, next];
    });
  };

  const handleUpdateLine = (lineId: string, patch: Partial<StagedLine>) => {
    setStaged((prev) =>
      prev.map((line) => (line.line_id === lineId ? { ...line, ...patch } : line)),
    );
  };

  const handleRemove = (lineId: string) => {
    setStaged((prev) => prev.filter((line) => line.line_id !== lineId));
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
        <EnquirySummaryHeader enquiry={enquiry} />

        <section className="space-y-3">
          <h3 className="text-foreground text-base font-semibold">{t("builder.criteria.title")}</h3>
          <QuoteCriteriaForm
            initial={initial}
            isSubmitting={search.isPending}
            onSubmit={handleSearch}
          />
        </section>

        <section className="space-y-3">
          <h3 className="text-foreground text-base font-semibold">{t("builder.results.title")}</h3>
          <QuoteResultsList
            options={results}
            hiddenForCapacity={hiddenForCapacity}
            isLoading={search.isPending && !isLoadingMore}
            stagedKeys={stagedKeys}
            onAdd={handleAdd}
            adults={lastCriteria?.adults ?? enquiry.adults}
            children={lastCriteria?.children ?? enquiry.children ?? 0}
            searchKey={
              lastCriteria
                ? `${lastCriteria.date_from}:${lastCriteria.date_to}:${lastCriteria.flex_days}`
                : ""
            }
            hasMore={hasMore}
            isLoadingMore={isLoadingMore}
            totalMatched={totalMatched}
            onLoadMore={() => void handleLoadMore()}
          />
        </section>

        {/* Shortlist sits at the foot as a full-width block in normal flow. The
            builder is plain vertical flow (criteria → results → shortlist) and lets
            its host own the column layout, so it reads the same scrolled
            top-to-bottom whatever pane it's mounted in — ending on Save draft /
            Send to guest. */}
        <QuoteShortlist
          lines={staged}
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
