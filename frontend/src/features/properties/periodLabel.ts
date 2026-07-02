import { formatWeekRangeCompact } from "@/lib/format/date";

/**
 * The single displayed label for a rate period: its operator name, with a
 * compact date-span fallback for any stray blank row. GAP-059 made the name
 * compulsory at every write surface, so the fallback is defensive only —
 * every consumer (timeline lanes, matrix, probe, plan detail) shares this one
 * rule instead of the five divergent renderings it replaced.
 */
export function periodLabel(period: {
  name?: string | null;
  date_from: string;
  date_to: string;
}): string {
  return period.name || formatWeekRangeCompact(period.date_from, period.date_to);
}
