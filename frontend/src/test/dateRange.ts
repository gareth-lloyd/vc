import { expect } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";

/** Structural slice of userEvent accepted by these helpers — both the direct
 * `userEvent` API and a `userEvent.setup()` instance satisfy it. */
interface DateRangeUser {
  click(element: Element): Promise<void>;
  clear(element: Element): Promise<void>;
  type(element: Element, text: string): Promise<void>;
}

/**
 * Helpers for dialogs using `DateRangePicker`. The picker's popover portals to
 * `document.body` (Radix), so its calendar and typed inputs are NOT inside the
 * host `<Dialog>` — `within(dialog)` queries can't see them. `openDateRange`
 * opens the picker and returns a query scope bound to the popover instead.
 */
export async function openDateRange(user: DateRangeUser, triggerName: RegExp | string) {
  await user.click(screen.getByRole("button", { name: triggerName }));
  // Combobox pickers (ContactPicker etc.) share the popover-content slot, so
  // require the calendar grid — which also waits until the popover is usable.
  const content = await waitFor(() => {
    const node = Array.from(
      document.querySelectorAll('[data-slot="popover-content"][data-state="open"]'),
    ).find((candidate) => candidate.querySelector('[role="grid"]'));
    if (!node) throw new Error("date-range popover did not open");
    return node as HTMLElement;
  });
  return within(content);
}

/** Type ISO values into the popover's From/To inputs (clearing any prefill). */
export async function typeDateRange(
  user: DateRangeUser,
  scope: ReturnType<typeof within>,
  range: { from?: string; to?: string },
  labels: { from: RegExp | string; to: RegExp | string } = { from: /^From$/, to: /^To$/ },
) {
  if (range.from !== undefined) {
    const input = scope.getByLabelText(labels.from);
    await user.clear(input);
    if (range.from) await user.type(input, range.from);
  }
  if (range.to !== undefined) {
    const input = scope.getByLabelText(labels.to);
    await user.clear(input);
    if (range.to) await user.type(input, range.to);
  }
}

/** Click calendar days by accessible name (e.g. /21 july 2026/i), in order. */
export async function clickDateRange(
  user: DateRangeUser,
  scope: ReturnType<typeof within>,
  ...dayNames: Array<RegExp | string>
) {
  for (const name of dayNames) {
    await user.click(scope.getByRole("button", { name }));
  }
}

/** Assert the (closed or open) trigger shows the expected formatted range. */
export function expectTriggerRange(triggerName: RegExp | string, expected: string | RegExp) {
  expect(screen.getByRole("button", { name: triggerName })).toHaveTextContent(expected);
}
