// A drop-in mock for the CodeMirror-backed `CodeField` used in jsdom tests.
// CodeMirror renders a contenteditable that doesn't behave under Testing
// Library, so editor/form tests `vi.mock` the real module to this textarea —
// same `value`/`onChange` contract, same accessible name — letting them drive
// the field like any other input and assert on OUR behaviour (validation,
// publish payload, preview wiring), never the library's internals.
interface CodeFieldProps {
  value: string;
  onChange: (value: string) => void;
  language?: "html" | "plain";
  ariaLabel: string;
  minHeight?: string;
}

export function CodeField({ value, onChange, ariaLabel }: CodeFieldProps) {
  return (
    <textarea aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)} />
  );
}
