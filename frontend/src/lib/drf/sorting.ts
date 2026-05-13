import type { SortingState } from "@tanstack/react-table";

export function sortingToOrdering(sorting: SortingState): string | undefined {
  if (!sorting.length) return undefined;
  const { id, desc } = sorting[0];
  return `${desc ? "-" : ""}${id}`;
}

export function orderingToSorting(ordering: string | undefined): SortingState {
  if (!ordering) return [];
  const desc = ordering.startsWith("-");
  const id = desc ? ordering.slice(1) : ordering;
  return [{ id, desc }];
}
