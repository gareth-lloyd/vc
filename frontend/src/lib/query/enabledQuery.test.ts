import { describe, expect, it, vi } from "vitest";
import { enabledQuery } from "./enabledQuery";

describe("enabledQuery", () => {
  it("disables the query when id is undefined", () => {
    const keyFor = vi.fn((id) => ["x", id] as const);
    const fetchFor = vi.fn(async (id: number) => ({ id }));
    const opts = enabledQuery<{ id: number }, number>(undefined, keyFor, fetchFor);
    expect(opts.enabled).toBe(false);
    expect(opts.queryKey).toEqual(["__disabled__"]);
    expect(keyFor).not.toHaveBeenCalled();
  });

  it("enables the query when id is given", () => {
    const keyFor = vi.fn((id) => ["x", id] as const);
    const fetchFor = vi.fn(async (id: number) => ({ id }));
    const opts = enabledQuery<{ id: number }, number>(7, keyFor, fetchFor);
    expect(opts.enabled).toBe(true);
    expect(opts.queryKey).toEqual(["x", 7]);
  });
});
