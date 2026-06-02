import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n";
import { StatusFilterBar } from "../StatusFilterBar";

function renderBar(props: Partial<Parameters<typeof StatusFilterBar>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <StatusFilterBar
        options={[
          { value: "confirmed", label: "Confirmed" },
          { value: "cancelled", label: "Cancelled" },
        ]}
        counts={{ confirmed: 3, cancelled: 1 }}
        value={undefined}
        onChange={onChange}
        allLabel="All"
        {...props}
      />
    </I18nextProvider>,
  );
  return { onChange };
}

describe("StatusFilterBar", () => {
  it("renders a chip per option plus an 'all' chip with the summed total", () => {
    renderBar();
    expect(screen.getByRole("tab", { name: /All/ })).toHaveTextContent("4");
    expect(screen.getByRole("tab", { name: /Confirmed/ })).toHaveTextContent("3");
    expect(screen.getByRole("tab", { name: /Cancelled/ })).toHaveTextContent("1");
  });

  it("marks the active status chip selected", () => {
    renderBar({ value: "confirmed" });
    expect(screen.getByRole("tab", { name: /Confirmed/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /^All/ })).toHaveAttribute("aria-selected", "false");
  });

  it("emits the status value on click and undefined for 'all'", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar({ value: "confirmed" });
    await user.click(screen.getByRole("tab", { name: /Cancelled/ }));
    expect(onChange).toHaveBeenCalledWith("cancelled");
    await user.click(screen.getByRole("tab", { name: /^All/ }));
    expect(onChange).toHaveBeenCalledWith(undefined);
  });

  it("shows zero counts when data has no entry for a status", () => {
    renderBar({ counts: { confirmed: 2 } });
    expect(screen.getByRole("tab", { name: /Cancelled/ })).toHaveTextContent("0");
  });
});
