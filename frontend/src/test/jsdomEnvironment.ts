import { builtinEnvironments, type Environment } from "vitest/environments";

/**
 * Vitest's stock jsdom environment, keeping Node's implementation of the
 * globals that Node's own `fetch` / `Request` (undici) brand-check.
 *
 * Vitest installs jsdom's `AbortController`, `AbortSignal`, `FormData` and
 * `File`, but the global `fetch` stays Node's. undici rejects a jsdom signal
 * ("RequestInit: Expected signal to be an instance of AbortSignal") — hit by
 * React Router's data router, which builds a `Request` on every completed
 * navigation (`renderWithDataRouter`) — and silently serialises a jsdom
 * `FormData` body as "[object FormData]". Restoring Node's classes puts
 * component code and fetch in one realm.
 *
 * Trade-off: the mismatch now sits on the DOM side instead. jsdom's
 * `EventTarget.addEventListener(type, fn, { signal })` brand-checks against
 * *jsdom's* `AbortSignal` and throws for a Node signal, and a Node abort
 * reason is not `instanceof` jsdom's `DOMException`. No src code relies on
 * either today; if a component adopts the `{ signal }` listener-cleanup idiom,
 * this file is why its test fails.
 *
 * Only `setup` is provided: the vm pools (`pool: "vmThreads" | "vmForks"`)
 * need `setupVM` and are unsupported with this environment.
 */
const NODE_REALM_KEYS = ["AbortController", "AbortSignal", "FormData", "File"] as const;

const jsdom = builtinEnvironments.jsdom;

const environment: Environment = {
  name: "jsdom-node-realm",
  transformMode: "web",
  async setup(global: typeof globalThis, options) {
    const nodeClasses = Object.fromEntries(NODE_REALM_KEYS.map((key) => [key, global[key]]));
    const env = await jsdom.setup(global, options);
    // Vitest installs jsdom globals as accessors whose setter records an
    // override, so plain assignment is enough.
    Object.assign(global, nodeClasses);
    return env;
  },
};

export default environment;
