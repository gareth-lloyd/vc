import { ALLOWED_EDGES, SANCTIONED_EDGES, DEBT_EDGES } from "../../boundaries.allowlist";

// Every production feature source, as raw text. Tests are excluded below to
// mirror the eslint boundaries block's exemptions.
const sources = import.meta.glob("/src/features/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function measuredEdges(): Set<string> {
  const edges = new Set<string>();
  for (const [path, code] of Object.entries(sources)) {
    if (path.includes("__tests__") || path.includes(".test.")) continue;
    const from = path.split("/")[3]; // "/src/features/<name>/…"
    for (const match of code.matchAll(/from "@\/features\/([a-z0-9-]+)/g)) {
      if (match[1] !== from) edges.add(`${from} -> ${match[1]}`);
    }
  }
  return edges;
}

function pairsOf(map: Record<string, readonly string[]>): string[] {
  return Object.entries(map).flatMap(([from, targets]) =>
    targets.map((target) => `${from} -> ${target}`),
  );
}

describe("module-boundary ratchet (GAP-063, GAP-072)", () => {
  it("every ALLOWED_EDGES entry is still exercised by production code", () => {
    const measured = measuredEdges();
    const stale = pairsOf(ALLOWED_EDGES).filter((edge) => !measured.has(edge));
    // A stale entry means the edge was paid down: delete it from the relevant
    // tier in boundaries.allowlist.js — the ratchet only shrinks.
    expect(stale).toEqual([]);
  });

  // Per-tier liveness gives a sharper failure message than the merged check
  // above (it names which tier holds the dead entry). GAP-072 split the flat
  // allowlist into SANCTIONED_EDGES (stable architecture) and DEBT_EDGES
  // (shrink-only coupling); both must stay live.
  it("every SANCTIONED_EDGES entry is still exercised by production code", () => {
    const measured = measuredEdges();
    const stale = pairsOf(SANCTIONED_EDGES).filter((edge) => !measured.has(edge));
    expect(stale).toEqual([]);
  });

  it("every DEBT_EDGES entry is still exercised by production code", () => {
    const measured = measuredEdges();
    const stale = pairsOf(DEBT_EDGES).filter((edge) => !measured.has(edge));
    expect(stale).toEqual([]);
  });

  // A pair is either sanctioned architecture or debt — never both, or the tier
  // labels mean nothing and the debt-shrinks-only rule is unenforceable.
  it("no pair appears in both tiers", () => {
    const sanctioned = new Set(pairsOf(SANCTIONED_EDGES));
    const overlap = pairsOf(DEBT_EDGES).filter((edge) => sanctioned.has(edge));
    expect(overlap).toEqual([]);
  });

  // ALLOWED_EDGES (the map eslint consumes) must be exactly the union of the
  // two tiers — no edge silently enforced by lint but absent from both tiers.
  it("ALLOWED_EDGES is the union of the two tiers", () => {
    expect(new Set(pairsOf(ALLOWED_EDGES))).toEqual(
      new Set([...pairsOf(SANCTIONED_EDGES), ...pairsOf(DEBT_EDGES)]),
    );
  });
});
