import type { UseQueryOptions } from "@tanstack/react-query";

const DISABLED_KEY = ["__disabled__"] as const;

export function enabledQuery<TData, TId extends string | number>(
  id: TId | undefined,
  keyFor: (id: TId) => readonly unknown[],
  fetchFor: (id: TId) => Promise<TData>,
): UseQueryOptions<TData, Error, TData, readonly unknown[]> {
  if (id == null) {
    return {
      queryKey: DISABLED_KEY,
      queryFn: () => Promise.reject(new Error("disabled")),
      enabled: false,
    };
  }
  return { queryKey: keyFor(id), queryFn: () => fetchFor(id), enabled: true };
}
