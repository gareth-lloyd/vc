import type { QueryClient } from "@tanstack/react-query";

// DEV-only frontend observability. Subscribes to the React Query caches and
// exposes ring buffers + the live client on `window` so the Playwright MCP
// server can read per-query-key fetch counts and observer state through
// `browser_evaluate`. Never shipped to production — see README.md and the
// `import.meta.env.DEV`-guarded dynamic import in `App.tsx`.

const RING_MAX = 2000;

export interface RqEvent {
  ts: number;
  /** QueryCache event type: added | removed | updated | observer* */
  type: string;
  queryHash: string;
  /** Present when `type === "updated"`: fetch | success | error | invalidate | … */
  actionType?: string;
}

export interface MutationEvent {
  ts: number;
  type: string;
  mutationKey?: unknown;
  status?: string;
}

export interface RenderEvent {
  ts: number;
  id: string;
  /** React Profiler phase: mount | update | nested-update */
  phase: string;
  duration: number;
}

interface DevtoolsWindow {
  __rqClient?: QueryClient;
  __rqLog?: RqEvent[];
  __mutLog?: MutationEvent[];
  __renderLog?: RenderEvent[];
  __rqReset?: () => void;
  __rqUnsubscribe?: () => void;
}

export function devWindow(): DevtoolsWindow {
  return window as unknown as DevtoolsWindow;
}

export function pushCapped<T>(buffer: T[], item: T, max = RING_MAX): void {
  buffer.push(item);
  if (buffer.length > max) buffer.splice(0, buffer.length - max);
}

/**
 * Subscribe to the query + mutation caches and publish the observation
 * surface on `window`. Idempotent across Vite HMR re-runs (tears down a prior
 * installation first).
 */
export function installQueryObserver(client: QueryClient): void {
  const w = devWindow();

  // Vite HMR can re-run this module with a fresh client; drop the old subs.
  w.__rqUnsubscribe?.();

  const rqLog: RqEvent[] = [];
  const mutLog: MutationEvent[] = [];

  const unsubscribeQueries = client.getQueryCache().subscribe((event) => {
    pushCapped(rqLog, {
      ts: Date.now(),
      type: event.type,
      queryHash: event.query.queryHash,
      actionType: event.type === "updated" ? event.action.type : undefined,
    });
  });

  const unsubscribeMutations = client.getMutationCache().subscribe((event) => {
    pushCapped(mutLog, {
      ts: Date.now(),
      type: event.type,
      mutationKey: event.mutation?.options.mutationKey,
      status: event.mutation?.state.status,
    });
  });

  w.__rqClient = client;
  w.__rqLog = rqLog;
  w.__mutLog = mutLog;
  w.__rqReset = () => {
    rqLog.length = 0;
    mutLog.length = 0;
    if (w.__renderLog) w.__renderLog.length = 0;
  };
  w.__rqUnsubscribe = () => {
    unsubscribeQueries();
    unsubscribeMutations();
  };

  console.info("[devtools] query observer installed — window.__rqLog / __rqClient ready");
}
