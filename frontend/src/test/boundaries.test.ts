import { ALLOWED_EDGES } from "../../boundaries.allowlist";

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

describe("module-boundary ratchet (GAP-063)", () => {
  it("every ALLOWED_EDGES entry is still exercised by production code", () => {
    const measured = measuredEdges();
    const stale = Object.entries(ALLOWED_EDGES)
      .flatMap(([from, targets]) => targets.map((target) => `${from} -> ${target}`))
      .filter((edge) => !measured.has(edge));
    // A stale entry means the edge was paid down: delete it from
    // boundaries.allowlist.js — the ratchet only shrinks.
    expect(stale).toEqual([]);
  });
});
