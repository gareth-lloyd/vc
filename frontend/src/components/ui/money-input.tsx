import * as React from "react";

import { cn } from "@/lib/cn";
import { Input } from "./input";

/**
 * An {@link Input} with an optional leading currency adornment (GAP-026). Pass
 * the resolved token (a symbol like "£", a bare code like "AED", or "%") via
 * `adornment`; a `null` adornment renders a plain input so callers can fall back
 * to a "set currency" prompt rather than show a blank prefix. All other props —
 * including the `ref`/`onChange` spread from `react-hook-form`'s `register` —
 * pass straight through to the underlying input.
 */
function MoneyInput({
  adornment,
  className,
  ...props
}: React.ComponentProps<"input"> & { adornment: string | null }) {
  // Always render the same element shape (wrapper + input) regardless of
  // `adornment`, so toggling it on/off (e.g. POA masking a price, or a finance
  // type switching to/from `inherit`) only flips a class — never remounts the
  // input, which would drop focus/caret/IME state. Widen the left padding for
  // multi-character tokens ("AED", "CHF") so they never overlap the value.
  const padding = adornment ? (adornment.length > 1 ? "pl-12" : "pl-9") : undefined;
  return (
    <div className="relative">
      {adornment ? (
        <span className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm">
          {adornment}
        </span>
      ) : null}
      <Input className={cn(padding, className)} {...props} />
    </div>
  );
}

export { MoneyInput };
