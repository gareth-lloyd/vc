/**
 * Format the backend's `coverage_gaps` — uncovered `[low, high]` party
 * sub-ranges of `1..max_occupancy` — as a compact human string ("3, 5–8").
 * A period with gaps cannot be activated (the serializer rejects it); the UI
 * surfaces this so staff can close the gap before flipping it active.
 */
export function formatPartyGaps(gaps: number[][]): string {
  return gaps.map(([low, high]) => (low === high ? `${low}` : `${low}–${high}`)).join(", ");
}
