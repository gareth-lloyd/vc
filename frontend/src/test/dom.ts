/** True when `a` comes before `b` in document order (for "X renders above Y"). */
export function precedes(a: Node, b: Node): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}
