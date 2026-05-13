import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { useLanguageSync } from "@/i18n/useLanguageSync";

export function AppProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  useLanguageSync();
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        {children}
        <Toaster richColors position="bottom-right" />
        {import.meta.env.DEV ? <ReactQueryDevtools initialIsOpen={false} /> : null}
      </TooltipProvider>
    </QueryClientProvider>
  );
}
