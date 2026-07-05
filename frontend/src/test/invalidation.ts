/** The query keys passed to every `invalidateQueries` call captured by a
 * `vi.spyOn(queryClient, "invalidateQueries")` spy. */
export function invalidatedKeys(spy: { mock: { calls: unknown[][] } }): unknown[] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown }).queryKey);
}
