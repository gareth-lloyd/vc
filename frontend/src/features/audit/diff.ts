/**
 * Interpret a raw `field_diffs` blob from the backend audit trail.
 *
 * The backend (`core/audit.py`) writes one of:
 *   - update / create: `{ field: [old, new], ... }` (a create has `old === null`
 *     on every field, but is NOT marked, so we don't claim "created");
 *   - delete:          `{ __deleted__: true, field: [old, null], ... }`;
 *   - merge:           a delete row plus `__merged_into__` (target pk) and
 *                      `__rewrites__` ({ "app.Model.field": count }).
 * Sensitive fields carry the literal `"[REDACTED]"` sentinel on either side.
 */

export type AuditAction = "updated" | "deleted" | "merged";

export interface DiffRow {
  field: string;
  before: unknown;
  after: unknown;
}

export interface InterpretedEntry {
  action: AuditAction;
  rows: DiffRow[];
  /** Destination pk for a merge tombstone, if any. */
  mergedInto?: string;
  /** Per-relation FK rewrite counts folded onto a merge tombstone. */
  rewrites?: Record<string, number>;
}

const CONTROL_KEYS = new Set(["__deleted__", "__merged_into__", "__rewrites__", "__created__"]);

export const REDACTED = "[REDACTED]";

export function interpretEntry(fieldDiffs: Record<string, unknown>): InterpretedEntry {
  const diffs = fieldDiffs ?? {};
  const mergedIntoRaw = diffs["__merged_into__"];
  const mergedInto = mergedIntoRaw == null ? undefined : String(mergedIntoRaw);
  const rewritesRaw = diffs["__rewrites__"];
  const rewrites =
    rewritesRaw && typeof rewritesRaw === "object"
      ? (rewritesRaw as Record<string, number>)
      : undefined;

  let action: AuditAction = "updated";
  if (mergedInto !== undefined) {
    action = "merged";
  } else if (diffs["__deleted__"]) {
    action = "deleted";
  }

  const rows: DiffRow[] = [];
  for (const [field, value] of Object.entries(diffs)) {
    if (CONTROL_KEYS.has(field)) continue;
    if (Array.isArray(value) && value.length === 2) {
      rows.push({ field, before: value[0], after: value[1] });
    } else {
      // Defensive: malformed / legacy shape — show the raw value as the new side.
      rows.push({ field, before: undefined, after: value });
    }
  }

  return { action, rows, mergedInto, rewrites };
}
