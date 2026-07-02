import { addDays, format, parseISO } from "date-fns";

const ISO = "yyyy-MM-dd";

/** A drag-selected block range, half-open `[date_from, date_to)` — `date_to` is
 * exclusive, matching the typed/picker path (`DateRangePicker` in nights mode
 * stores `date_to = lastNight + 1`) and the backend's overlap predicates. */
export interface DragRange {
  date_from: string;
  date_to: string;
}

/**
 * Resolve a press-drag-release on the month grid into a block range.
 *
 * Anchored on `originIso` (the press day, which the grid only lets drags start
 * on when it is selectable): the selection walks toward `releaseIso` and stops
 * **before** the first non-selectable day, so a drag can't span an occupied /
 * booked day — it truncates on the moving side, mirroring the dialog's
 * occupied-day greying. A single-day drag yields a one-night range. Returns
 * `null` if the origin isn't selectable (defensive — the grid shouldn't allow
 * it).
 */
export function resolveDragRange(
  originIso: string,
  releaseIso: string,
  isSelectable: (iso: string) => boolean,
): DragRange | null {
  if (!isSelectable(originIso)) return null;
  const step = releaseIso < originIso ? -1 : 1;
  let last = originIso;
  let cursor = originIso;
  while (cursor !== releaseIso) {
    const next = format(addDays(parseISO(cursor), step), ISO);
    if (!isSelectable(next)) break;
    last = next;
    cursor = next;
  }
  // Origin and `last` are both selectable; span them inclusively, then emit the
  // exclusive end (last selectable night + 1).
  const earliest = last < originIso ? last : originIso;
  const latest = last < originIso ? originIso : last;
  return { date_from: earliest, date_to: format(addDays(parseISO(latest), 1), ISO) };
}
