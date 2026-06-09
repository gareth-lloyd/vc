import type { FieldErrors } from "react-hook-form";

interface Props {
  message: string | null;
  // Opt-in summary: when a form passes its `formState.errors`, every field-error
  // message is listed beneath the detail. Without this, a field error mapped
  // inline by `applyApiErrorToForm` (or by the Zod resolver) has no home and is
  // silently dropped unless the form renders each field's error itself.
  fieldErrors?: FieldErrors;
}

function collectMessages(errors: FieldErrors | undefined): string[] {
  if (!errors) return [];
  const out: string[] = [];
  for (const entry of Object.values(errors)) {
    const message = (entry as { message?: unknown } | undefined)?.message;
    if (typeof message === "string" && message) out.push(message);
  }
  return out;
}

export function FormErrorAlert({ message, fieldErrors }: Props) {
  const details = collectMessages(fieldErrors);
  if (!message && details.length === 0) return null;
  return (
    <div
      className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
      role="alert"
    >
      {message ? <p>{message}</p> : null}
      {details.length > 0 ? (
        <ul className="list-disc ps-5">
          {details.map((d, i) => (
            <li key={`${i}-${d}`}>{d}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
