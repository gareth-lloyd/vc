import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useCopyToClipboard } from "../useCopyToClipboard";

const originalClipboard = navigator.clipboard;
const originalClipboardItem = (globalThis as { ClipboardItem?: unknown }).ClipboardItem;

afterEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: originalClipboard,
    configurable: true,
  });
  (globalThis as { ClipboardItem?: unknown }).ClipboardItem = originalClipboardItem;
  vi.restoreAllMocks();
});

describe("useCopyToClipboard", () => {
  it("writes both text/html and text/plain via ClipboardItem when available", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { write, writeText: vi.fn() },
      configurable: true,
    });
    class FakeClipboardItem {
      items: Record<string, Blob>;
      constructor(items: Record<string, Blob>) {
        this.items = items;
      }
    }
    (globalThis as { ClipboardItem?: unknown }).ClipboardItem = FakeClipboardItem;

    const { result } = renderHook(() => useCopyToClipboard());
    let ok = false;
    await act(async () => {
      ok = await result.current.copy("<b>hi</b>", "hi");
    });

    expect(ok).toBe(true);
    expect(write).toHaveBeenCalledTimes(1);
    const item = write.mock.calls[0][0][0] as FakeClipboardItem;
    expect(Object.keys(item.items)).toEqual(["text/html", "text/plain"]);
    expect(result.current.copied).toBe(true);
  });

  it("falls back to writeText when ClipboardItem is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    (globalThis as { ClipboardItem?: unknown }).ClipboardItem = undefined;

    const { result } = renderHook(() => useCopyToClipboard());
    let ok = false;
    await act(async () => {
      ok = await result.current.copy("<b>hi</b>", "hi");
    });

    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hi");
  });

  it("returns false when no clipboard API exists", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    const { result } = renderHook(() => useCopyToClipboard());
    let ok = true;
    await act(async () => {
      ok = await result.current.copy("<b>hi</b>");
    });
    expect(ok).toBe(false);
  });
});
