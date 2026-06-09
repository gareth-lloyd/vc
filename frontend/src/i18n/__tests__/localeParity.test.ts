import { describe, expect, it } from "vitest";
import { I18N_NAMESPACES } from "../index";

// Eagerly load every locale JSON so the test sees the on-disk source of truth.
const enModules = import.meta.glob("../locales/en/*.json", { eager: true });
const elModules = import.meta.glob("../locales/el/*.json", { eager: true });

type Json = Record<string, unknown>;

function moduleFor(modules: Record<string, unknown>, ns: string): Json {
  const entry = Object.entries(modules).find(([path]) => path.endsWith(`/${ns}.json`));
  if (!entry) throw new Error(`No locale file for namespace "${ns}"`);
  return (entry[1] as { default: Json }).default;
}

// Flatten a nested message tree into dotted keys → string value.
function flatten(obj: Json, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      for (const [k, v] of flatten(value as Json, path)) out.set(k, v);
    } else if (typeof value === "string") {
      out.set(path, value);
    }
  }
  return out;
}

// Interpolation tokens — {{count}}, {{name}} — must survive translation.
function placeholders(value: string): Set<string> {
  return new Set([...value.matchAll(/\{\{\s*([\w.]+)\s*}}/g)].map((m) => m[1]));
}

describe("locale parity (en ↔ el)", () => {
  it.each([...I18N_NAMESPACES])("namespace %s has identical key sets", (ns) => {
    const en = flatten(moduleFor(enModules, ns));
    const el = flatten(moduleFor(elModules, ns));
    const missingInEl = [...en.keys()].filter((k) => !el.has(k));
    const extraInEl = [...el.keys()].filter((k) => !en.has(k));
    expect(
      { missingInEl, extraInEl },
      `[${ns}] missing in el: ${missingInEl.join(", ") || "none"} | extra in el: ${extraInEl.join(", ") || "none"}`,
    ).toEqual({ missingInEl: [], extraInEl: [] });
  });

  it.each([...I18N_NAMESPACES])("namespace %s keeps placeholder tokens in sync", (ns) => {
    const en = flatten(moduleFor(enModules, ns));
    const el = flatten(moduleFor(elModules, ns));
    const mismatches: string[] = [];
    for (const [key, enValue] of en) {
      const elValue = el.get(key);
      if (elValue === undefined) continue; // key-set test owns missing keys
      const enTokens = [...placeholders(enValue)].sort();
      const elTokens = [...placeholders(elValue)].sort();
      if (enTokens.join(",") !== elTokens.join(",")) {
        mismatches.push(`${key} (en: {${enTokens}} el: {${elTokens}})`);
      }
    }
    expect(mismatches, `[${ns}] placeholder drift:\n${mismatches.join("\n")}`).toEqual([]);
  });
});
