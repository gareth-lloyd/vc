import { parseISO } from "date-fns";

/**
 * Days the block-range picker greys out: every occupied availability cell, as a
 * `Date`. In a block's *edit* dialog pass `editingBlockId` so the block's own
 * cells stay selectable; omit it (owner portal, create mode) to disable every
 * occupied day. Shared by both block dialogs so they can't drift.
 */
export function disabledDaysFromCells(
  cells: { date: string; available: boolean; block_id?: number | null }[],
  editingBlockId: number | null = null,
): Date[] {
  // Booked cells carry an explicit `block_id: null`, so the create-mode null
  // sentinel must not compare against it — only a real block id exempts cells.
  return cells
    .filter(
      (cell) => !cell.available && (editingBlockId === null || cell.block_id !== editingBlockId),
    )
    .map((cell) => parseISO(cell.date));
}
