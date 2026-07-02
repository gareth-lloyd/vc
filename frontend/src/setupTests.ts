import "@testing-library/jest-dom/vitest";
import { File as NodeFile } from "node:buffer";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./test/msw/server";

// Vitest's jsdom environment installs jsdom's FormData/File globals, but the
// global `fetch` is Node's (undici), which doesn't recognise them — a
// multipart body silently serialises as the string "[object FormData]".
// Replace them with Node's own classes so component code and fetch share one
// realm. (Node doesn't export FormData from any module; recover the class via
// a Response round-trip.)
const nodeFormDataClass = (
  await new Response("probe=1", {
    headers: { "content-type": "application/x-www-form-urlencoded" },
  }).formData()
).constructor;
globalThis.FormData = nodeFormDataClass as typeof FormData;
globalThis.File = NodeFile as unknown as typeof File;

// jsdom polyfills for Radix primitives
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverPolyfill as never);

// jsdom has no matchMedia; default to `matches: false` (narrow viewport) so
// media-query-driven components take their single-column branch in tests.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
