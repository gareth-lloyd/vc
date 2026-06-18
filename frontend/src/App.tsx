import { RouterProvider } from "react-router-dom";
import { AppProviders } from "@/app/providers";
import { router } from "@/app/router";
import { DevProfiler } from "@/lib/devtools/DevProfiler";
import { createQueryClient } from "@/lib/query/client";

const queryClient = createQueryClient();

if (import.meta.env.DEV) {
  // DEV-only frontend observability for the Playwright MCP server. Dropped
  // from production builds (the whole branch is dead-code-eliminated).
  void import("@/lib/devtools/observe").then((m) => m.installQueryObserver(queryClient));
}

export function App() {
  const tree = <RouterProvider router={router} />;
  return (
    <AppProviders client={queryClient}>
      {import.meta.env.DEV ? <DevProfiler id="app">{tree}</DevProfiler> : tree}
    </AppProviders>
  );
}
