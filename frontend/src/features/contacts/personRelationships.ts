// GAP-041 F2: the seven person-relationship kinds. A relationship is stored
// once (from_person → to_person) but rendered from both sides: an OUTGOING row
// (this contact is the from_person) reads with the forward label, while the
// mirror INCOMING row (this contact is the to_person) reads with the inverse
// label — e.g. "A is B's child" appears on B's profile as "Parent".

// Forward kinds, in canonical order, used by the create <select> and for
// OUTGOING rows. `labelKey` resolves under `relationship_kinds.<value>`.
export const RELATIONSHIP_KINDS: readonly { value: string; labelKey: string }[] = [
  { value: "spouse", labelKey: "relationship_kinds.spouse" },
  { value: "partner", labelKey: "relationship_kinds.partner" },
  { value: "child", labelKey: "relationship_kinds.child" },
  { value: "parent", labelKey: "relationship_kinds.parent" },
  { value: "pa", labelKey: "relationship_kinds.pa" },
  { value: "sibling", labelKey: "relationship_kinds.sibling" },
  { value: "other", labelKey: "relationship_kinds.other" },
];

const KNOWN_KINDS = new Set(RELATIONSHIP_KINDS.map((k) => k.value));

/**
 * The i18n key for a relationship's localized label. OUTGOING rows use the
 * forward label (`relationship_kinds.*`); INCOMING rows use the inverse label
 * (`relationship_inverse.*`). An unknown kind falls back to its raw value so
 * the chip degrades gracefully rather than rendering a missing-key string.
 */
export function relationshipLabelKey(kind: string, direction: "outgoing" | "incoming"): string {
  if (!KNOWN_KINDS.has(kind)) return kind;
  return direction === "incoming" ? `relationship_inverse.${kind}` : `relationship_kinds.${kind}`;
}
