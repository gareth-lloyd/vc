import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { html } from "@codemirror/lang-html";
import type { Extension } from "@codemirror/state";

// The ONLY module that imports CodeMirror. Everything else depends on this thin
// controlled wrapper, which the editor/form tests mock to a plain `<textarea>`
// (see `src/test/mocks/codeField.tsx`) — so we exercise our own form,
// validation and preview wiring without running CodeMirror's contenteditable in
// jsdom. We test our integration, never the library.
interface CodeFieldProps {
  value: string;
  onChange: (value: string) => void;
  language?: "html" | "plain";
  ariaLabel: string;
  minHeight?: string;
}

export function CodeField({
  value,
  onChange,
  language = "plain",
  ariaLabel,
  minHeight = "16rem",
}: CodeFieldProps) {
  const extensions = useMemo<Extension[]>(() => (language === "html" ? [html()] : []), [language]);
  return (
    <div className="border-border overflow-hidden rounded-md border">
      <CodeMirror
        value={value}
        onChange={onChange}
        extensions={extensions}
        minHeight={minHeight}
        aria-label={ariaLabel}
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
      />
    </div>
  );
}
