import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  createCurrency,
  deleteCurrency,
  fetchCurrencies,
  fetchCurrency,
  updateCurrency,
} from "./api";
import type { CurrencyFilters, CurrencyWriteInput } from "./schemas";

export function useCurrencies(filters: CurrencyFilters) {
  return useQuery({
    queryKey: queryKeys.currencies.list(filters),
    queryFn: () => fetchCurrencies(filters),
  });
}

export function useCurrency(code: string | undefined) {
  return useQuery({
    queryKey: code ? queryKeys.currencies.detail(code) : ["currencies", "detail", "__disabled__"],
    queryFn: () => fetchCurrency(code as string),
    enabled: !!code,
  });
}

export function useCreateCurrency() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CurrencyWriteInput) => createCurrency(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.currencies.lists() });
    },
  });
}

export function useUpdateCurrency(code: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CurrencyWriteInput>) => updateCurrency(code, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.currencies.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.currencies.detail(code) });
    },
  });
}

export function useDeleteCurrency(code: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCurrency(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.currencies.lists() });
    },
  });
}
