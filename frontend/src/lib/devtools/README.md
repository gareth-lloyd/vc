# Frontend runtime observability (DEV only)

A tiny instrumentation layer for driving the SPA with the **Playwright MCP
server** and catching two classes of misbehavior at runtime:

1. **Repeated / looping API requests** — a query key that refetches over and
   over, an endpoint hammered N times, a fetch storm after a mutation.
2. **Flapping components** — a subtree that re-renders far more than it should,
   or a genuine render loop.

Everything here is **DEV only** and tree-shaken out of production builds — it is
referenced solely behind `import.meta.env.DEV` guards in `App.tsx`
(`installQueryObserver` via a dynamic `import()`, `DevProfiler` via a ternary).
The `/observe-route` slash command wraps the recipe below.

## What gets installed

`installQueryObserver(queryClient)` subscribes to the React Query query and
mutation caches and publishes these on `window`:

| Global                     | Type                       | Purpose                                                                      |
| -------------------------- | -------------------------- | ---------------------------------------------------------------------------- |
| `window.__rqClient`        | `QueryClient`              | The live client — read the cache directly (`getQueryCache()` …).             |
| `window.__rqLog`           | `RqEvent[]` (cap 2000)     | Ring buffer of query-cache events `{ ts, type, queryHash, actionType }`.     |
| `window.__mutLog`          | `MutationEvent[]`          | Ring buffer of mutation-cache events `{ ts, type, mutationKey, status }`.    |
| `window.__renderLog`       | `RenderEvent[]` (cap 5000) | Profiler commits `{ ts, id, phase, duration }` (populated by `DevProfiler`). |
| `window.__rqReset()`       | `() => void`               | Clears all three buffers — call before a measurement window.                 |
| `window.__rqUnsubscribe()` | `() => void`               | Detaches the cache subscriptions.                                            |

`RqEvent.actionType` is set when `type === "updated"` and is the React Query
action: `fetch | success | error | invalidate | setState | …`. **Counting
`actionType === "fetch"` per `queryHash` is the core refetch-loop signal.**

`DevProfiler` wraps `<RouterProvider>` (id `"app"`) in `App.tsx`. For sharper
attribution, wrap a suspect subtree in its own profiler, gated on DEV:

```tsx
{
  import.meta.env.DEV ? <DevProfiler id="quote-preview">{node}</DevProfiler> : node;
}
```

## `browser_evaluate` readers

Paste these as the function argument to the Playwright `browser_evaluate` tool.

```js
// (1) Query keys with > n fetches in a trailing window. Arg: {n:3, windowMs:5000}
({ n, windowMs }) => {
  const now = Date.now();
  const log = (window.__rqLog || []).filter(
    (e) => e.type === "updated" && e.actionType === "fetch" && now - e.ts <= windowMs,
  );
  const c = {};
  for (const e of log) c[e.queryHash] = (c[e.queryHash] || 0) + 1;
  return Object.entries(c).filter(([, v]) => v > n);
};
```

```js
// (2) Live cache snapshot — observer counts + fetch state, independent of the buffer.
() =>
  window.__rqClient
    .getQueryCache()
    .getAll()
    .map((q) => ({
      hash: q.queryHash,
      status: q.state.status, // pending | error | success
      fetchStatus: q.state.fetchStatus, // fetching | paused | idle
      dataUpdateCount: q.state.dataUpdateCount, // climbs once per successful fetch
      fetchFailureCount: q.state.fetchFailureCount,
      observers: q.getObserversCount(),
    }));
```

```js
// (3) Profiler commit counts per id in a window. Arg: {windowMs:5000}
({ windowMs }) => {
  const now = Date.now();
  const log = (window.__renderLog || []).filter((r) => now - r.ts <= windowMs);
  const c = {};
  for (const r of log) c[r.id] = (c[r.id] || 0) + 1;
  return Object.entries(c).sort((a, b) => b[1] - a[1]);
};
```

```js
// (4) Mutation events in a window (ties a fetch storm back to an invalidation). Arg: {windowMs:5000}
({ windowMs }) => {
  const now = Date.now();
  return (window.__mutLog || []).filter((e) => now - e.ts <= windowMs);
};
```

## Observation recipe

Prereq: DB + dev servers up (`docker compose up -d db`, `make dev-backend`,
`make dev-frontend`). Login: `glloyd@gmail.com` / `fiery-kite-pumpkin-eton`.

1. `browser_navigate` → `http://localhost:5173`; log in.
2. `browser_navigate` → the target route.
3. **Reset**: `browser_evaluate` → `() => window.__rqReset?.()`.
4. **Idle baseline**: `browser_wait_for` ~3s with no interaction. Catches loops
   that fire with zero user action (e.g. `refetchOnWindowFocus: true` + an
   unstable query key).
5. **Interact**: `browser_click` / `browser_type` the suspect affordance.
6. `browser_wait_for` ~5s to let a loop manifest.
7. **Pull signals**: `browser_network_requests` (per-endpoint counts) + readers
   (1)–(4) + `browser_console_messages`.

## Heuristics — flag a problem when

- Same `queryHash` fetched **> 3× in 5s with no user action** → refetch loop.
  Prime suspect: an object/array built inline in render and passed into a query
  key (a new `queryHash` every render).
- Same `/api/v1/...` endpoint requested **> N×** in the window (network-level
  corroboration; also catches non-React-Query fetches).
- `dataUpdateCount` / buffered fetch count **climbing while idle** → background
  loop.
- Profiler commit count for one `id` **climbing while idle**, or repeated
  `phase: "nested-update"` → flapping component.
- **"Maximum update depth exceeded"** in `browser_console_messages` →
  definitive synchronous render loop; report immediately.
- A mutation emitting a wave of `invalidate` events across many `queryHash`es
  (reader 4 + reader 1) followed by a fetch burst → over-broad invalidation.

## Known spots worth checking first

- `features/quotations/hooks.ts` — `useQuotationPreview` passes an `overrides`
  object into the query key (debounced 350ms in `SendPreviewDialog.tsx`).
- `features/admin/email-templates/hooks.ts` — `useEmailTemplatePreview`; the
  `PreviewPane.tsx` caller stabilizes the request with `useMemo` (good negative
  control — the detector should report **no** loop here).
- `features/bookings/hooks.ts` — status-transition mutations invalidate lists +
  status-counts + dashboard + activity + detail.
- Global `refetchOnWindowFocus: true` (`lib/query/client.ts`).

## Deep dive: react-scan (ad-hoc, no repo change)

For a focused render audit, inject [react-scan](https://github.com/aidenybai/react-scan)
at runtime with `browser_evaluate` — no dependency is added to `package.json`:

```js
() => {
  const s = document.createElement("script");
  s.src = "https://unpkg.com/react-scan/dist/auto.global.js";
  document.head.appendChild(s);
};
```

It paints re-render outlines and logs offenders to the console
(`browser_console_messages`). Keep it ad-hoc — the committed Profiler buffer is
the always-available signal.
