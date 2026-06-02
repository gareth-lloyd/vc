import { useCallback, useRef, useState } from "react";

interface CopyToClipboard {
  // Copies `html` as rich text plus `text` (defaults to `html`) as plain
  // text, so a paste into Outlook keeps formatting. Resolves true on success.
  copy: (html: string, text?: string) => Promise<boolean>;
  copied: boolean;
}

const RESET_MS = 2000;

// Generic clipboard helper. Prefers `navigator.clipboard.write` with both
// `text/html` and `text/plain` flavours (rich paste into Outlook/Gmail),
// falling back to `writeText` where `ClipboardItem`/`write` is unavailable.
export function useCopyToClipboard(): CopyToClipboard {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const markCopied = useCallback(() => {
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), RESET_MS);
  }, []);

  const copy = useCallback(
    async (html: string, text?: string): Promise<boolean> => {
      const plain = text ?? html;
      const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : undefined;
      if (!clipboard) return false;

      try {
        if (typeof ClipboardItem !== "undefined" && typeof clipboard.write === "function") {
          const item = new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([plain], { type: "text/plain" }),
          });
          await clipboard.write([item]);
          markCopied();
          return true;
        }
      } catch {
        // Fall through to the plain-text path below.
      }

      try {
        if (typeof clipboard.writeText === "function") {
          await clipboard.writeText(plain);
          markCopied();
          return true;
        }
      } catch {
        return false;
      }
      return false;
    },
    [markCopied],
  );

  return { copy, copied };
}
