import { describe, expect, it } from "vitest";
import { z } from "zod";
import { paginated } from "./pagination";

describe("paginated", () => {
  it("parses a paginated payload of items", () => {
    const schema = paginated(z.object({ id: z.number() }));
    const parsed = schema.parse({
      count: 3,
      next: "http://api/?page=2",
      previous: null,
      results: [{ id: 1 }, { id: 2 }, { id: 3 }],
    });
    expect(parsed.count).toBe(3);
    expect(parsed.next).toBe("http://api/?page=2");
    expect(parsed.previous).toBeNull();
    expect(parsed.results.map((r) => r.id)).toEqual([1, 2, 3]);
  });

  it("rejects missing required fields", () => {
    const schema = paginated(z.object({ id: z.number() }));
    expect(() => schema.parse({ count: 0, results: [] })).toThrow();
  });
});
