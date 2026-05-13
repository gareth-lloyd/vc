import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { createCountry, deleteCountry, fetchCountries, fetchCountry, updateCountry } from "./api";
import type { CountryFilters, CountryWriteInput } from "./schemas";

export function useCountries(filters: CountryFilters) {
  return useQuery({
    queryKey: queryKeys.countries.list(filters),
    queryFn: () => fetchCountries(filters),
  });
}

export function useCountry(iso2: string | undefined) {
  return useQuery({
    queryKey: iso2 ? queryKeys.countries.detail(iso2) : ["countries", "detail", "__disabled__"],
    queryFn: () => fetchCountry(iso2 as string),
    enabled: !!iso2,
  });
}

export function useCreateCountry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CountryWriteInput) => createCountry(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.countries.lists() });
    },
  });
}

export function useUpdateCountry(iso2: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CountryWriteInput>) => updateCountry(iso2, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.countries.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.countries.detail(iso2) });
    },
  });
}

export function useDeleteCountry(iso2: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCountry(iso2),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.countries.lists() });
    },
  });
}
