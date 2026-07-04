import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

/** A status-chip's "all" choice — treated as "param unset". */
const ALL_VALUE = "__all__";
const SEARCH_DEBOUNCE_MS = 250;

/**
 * Shared URL-list-controls plumbing for the index pages: a debounced search box
 * bound to `?q=`, plus param/page mutators that reset pagination on a filter
 * change. Page-specific parsing (status enums, view mode, related-id filters)
 * stays in each page's own `paramsToFilters`; this hook only owns the bits that
 * were byte-for-byte duplicated across them.
 */
export function useListParams() {
  const [params, setParams] = useSearchParams();
  const currentQ = params.get("q") ?? "";
  const [search, setSearch] = useState(currentQ);

  // Re-sync the box when `q` changes outside it (back/forward, a deep link).
  useEffect(() => {
    setSearch(currentQ);
  }, [currentQ]);

  // Debounce box → `?q=`; a new query resets pagination to page 1.
  useEffect(() => {
    if (search === currentQ) return;
    const handle = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (search) next.set("q", search);
          else next.delete("q");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [search, currentQ, setParams]);

  // Multi-key variant for dependent filters (e.g. changing country must also
  // clear region) — one setParams call, so one history entry.
  const updateParams = (entries: Record<string, string | undefined>) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(entries)) {
          if (value && value !== ALL_VALUE) next.set(key, value);
          else next.delete(key);
        }
        next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  const updateParam = (key: string, value: string | undefined) => updateParams({ [key]: value });

  const goToPage = (zeroBased: number) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (zeroBased <= 0) next.delete("page");
        else next.set("page", String(zeroBased + 1));
        return next;
      },
      { replace: true },
    );
  };

  return { params, setParams, search, setSearch, updateParam, updateParams, goToPage };
}
