import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettierConfig from "eslint-config-prettier";
import boundaries from "eslint-plugin-boundaries";
import { ALLOWED_EDGES } from "./boundaries.allowlist.js";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // shadcn-copied primitives intentionally mix component + helper exports.
    // Treat them as vendor source.
    files: ["src/components/ui/**/*.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    // GAP-063: enforce feature module boundaries (frontend analogue of the
    // backend's import-linter, FG-013). Only `src/features/*` directories are
    // elements, so ONLY feature→feature edges are constrained — app/, lib/,
    // components/, i18n/ importing features stays unconstrained by design
    // (incl. the pre-existing lib/auth → features/auth/store inversion).
    // Nested dirs fold into their parent element: properties/rate-workbench
    // classifies as "properties". Tests are exempt: cross-feature MSW
    // handlers / scaffolding are fine.
    files: ["src/features/**/*.{ts,tsx}"],
    ignores: ["**/__tests__/**", "**/*.test.*"],
    plugins: { boundaries },
    settings: {
      // Pin paths to this directory so the ratchet can't go silently inert if
      // eslint ever runs with a different cwd (the plugin defaults to cwd).
      "boundaries/root-path": import.meta.dirname,
      "boundaries/elements": [{ type: "feature", pattern: "src/features/*", capture: ["name"] }],
      "import/resolver": {
        typescript: { project: `${import.meta.dirname}/tsconfig.app.json` },
      },
    },
    rules: {
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          message:
            "feature '${file.name}' must not import feature '${dependency.name}'. " +
            "Move shared code to src/lib/ or src/components/; ALLOWED_EDGES entries " +
            "are for pre-existing coupling only and may only shrink.",
          rules: Object.entries(ALLOWED_EDGES).map(([from, targets]) => ({
            from: { type: "feature", captured: { name: from } },
            allow: targets.map((name) => ({ to: { type: "feature", captured: { name } } })),
          })),
        },
      ],
    },
  },
  prettierConfig,
);
