import type { ReactElement, ReactNode } from "react";
import { render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

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

export type ProviderRenderResult = RenderResult & { queryClient: QueryClient };

export function renderWithProviders(ui: ReactElement, options: Options = {}): ProviderRenderResult {
  const queryClient = options.queryClient ?? createTestQueryClient();
  const initialEntries = options.routerProps?.initialEntries ?? [options.route ?? "/"];
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter {...options.routerProps} initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
  const rendered = render(ui, { wrapper: Wrapper });
  return Object.assign(rendered, { queryClient });
}
