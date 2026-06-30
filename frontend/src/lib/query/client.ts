import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { ApiError } from "@/lib/api/errors";

// A response that fails its Zod schema throws a ZodError from inside the
// queryFn (the api layer parses every response). React Query stores that as
// the query's error and renders the error boundary, but logs nothing — so a
// backend field rename reads as a silent "couldn't load" with a 200 in the
// Network tab. Surface it loudly in dev, with the field-level detail.
export function logQueryError(scope: string, key: unknown, error: unknown): void {
  if (!import.meta.env.DEV) return;
  if (error instanceof z.ZodError) {
    console.error(
      `[${scope}] response failed schema validation`,
      key,
      "\n" + z.prettifyError(error),
    );
  } else if (!(error instanceof ApiError)) {
    // ApiErrors already surface via the UI and the Network tab; only the
    // unexpected (parse, programmer, network) errors need a console nudge.
    console.error(`[${scope}]`, key, error);
  }
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  // A schema mismatch is deterministic — retrying just triples the traffic and
  // delays the error reaching the boundary.
  if (error instanceof z.ZodError) return false;
  if (error instanceof ApiError && error.isClientError()) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => logQueryError("query", query.queryKey, error),
    }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) =>
        logQueryError("mutation", mutation.options.mutationKey, error),
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
        retry: shouldRetryQuery,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
