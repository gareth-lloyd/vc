import type { ReactElement, ReactNode } from "react";
import { cleanup, render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  MemoryRouter,
  RouterProvider,
  createMemoryRouter,
  type DataRouter,
  type MemoryRouterProps,
  type RouteObject,
} from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { afterEach } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import i18n from "@/i18n";

interface Options {
  route?: string;
  routerProps?: Omit<MemoryRouterProps, "children">;
  queryClient?: QueryClient;
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

/** The app-level provider stack shared by both render helpers (router excluded). */
function withTestProviders(queryClient: QueryClient, children: ReactNode): ReactElement {
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>{children}</TooltipProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

export type ProviderRenderResult = RenderResult & { queryClient: QueryClient };

export function renderWithProviders(ui: ReactElement, options: Options = {}): ProviderRenderResult {
  const queryClient = options.queryClient ?? createTestQueryClient();
  const initialEntries = options.routerProps?.initialEntries ?? [options.route ?? "/"];
  const Wrapper = ({ children }: { children: ReactNode }) =>
    withTestProviders(
      queryClient,
      <MemoryRouter {...options.routerProps} initialEntries={initialEntries}>
        {children}
      </MemoryRouter>,
    );
  const rendered = render(ui, { wrapper: Wrapper });
  return Object.assign(rendered, { queryClient });
}

/**
 * No `rerender`: the tree is defined by `routes`, so drive changes through
 * `router.navigate()` instead.
 */
export type DataRouterRenderResult = Omit<RenderResult, "rerender"> & {
  queryClient: QueryClient;
  router: DataRouter;
};

// RouterProvider only unsubscribes on unmount; the router's own window
// listener and any in-flight navigation outlive the test unless disposed.
// Unmount first (RTL's own cleanup hook runs later in the afterEach stack) so
// the provider never observes a disposed router.
const liveRouters = new Set<DataRouter>();
afterEach(() => {
  cleanup();
  for (const router of liveRouters) router.dispose();
  liveRouters.clear();
});

/**
 * Like `renderWithProviders`, but mounts a **data router** (`createMemoryRouter`
 * + `RouterProvider`). Required for anything using data-router-only hooks such
 * as `useBlocker`, which throw under a plain `<MemoryRouter>`. Returns the
 * `router` so tests can assert `router.state.location.pathname`.
 */
export function renderWithDataRouter(
  routes: RouteObject[],
  options: Omit<Options, "routerProps"> = {},
): DataRouterRenderResult {
  const queryClient = options.queryClient ?? createTestQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [options.route ?? "/"] });
  liveRouters.add(router);
  const rendered = render(withTestProviders(queryClient, <RouterProvider router={router} />));
  return Object.assign(rendered, { queryClient, router });
}
