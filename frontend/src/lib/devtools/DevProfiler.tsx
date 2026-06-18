import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from "react";
import { devWindow, pushCapped } from "./observe";

// DEV-only React Profiler wrapper. Commit records land in `window.__renderLog`
// for the Playwright MCP server to read (see README.md). The whole devtools
// folder is tree-shaken out of production builds — it's only referenced behind
// `import.meta.env.DEV` guards in `App.tsx` — but we no-op defensively too.

const RENDER_MAX = 5000;

export function DevProfiler({ id, children }: { id: string; children: ReactNode }): ReactNode {
  if (!import.meta.env.DEV) return children;

  const onRender: ProfilerOnRenderCallback = (profilerId, phase, actualDuration) => {
    const w = devWindow();
    const log = (w.__renderLog ??= []);
    pushCapped(
      log,
      { ts: Date.now(), id: profilerId, phase, duration: actualDuration },
      RENDER_MAX,
    );
  };

  return (
    <Profiler id={id} onRender={onRender}>
      {children}
    </Profiler>
  );
}
