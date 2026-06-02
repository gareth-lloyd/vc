import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { IconPicker } from "../IconPicker";

vi.mock("lucide-react/dynamic", () => ({
  iconNames: ["wifi", "waves", "flame", "tv", "bath"],
  DynamicIcon: ({ name }: { name: string }) => <svg data-testid={`dyn-${name}`} />,
}));

function Harness({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <IconPicker value={value} onChange={setValue} aria-label="Icon" />
      <span data-testid="value">{value || "(empty)"}</span>
    </>
  );
}

describe("IconPicker", () => {
  it("filters icons by search and selects one", async () => {
    renderWithProviders(<Harness />);
    await userEvent.click(screen.getByRole("combobox", { name: "Icon" }));
    await userEvent.type(screen.getByLabelText(/search icons/i), "wif");
    await userEvent.click(await screen.findByRole("option", { name: "wifi" }));
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("wifi"));
  });

  it("shows a no-results message when nothing matches", async () => {
    renderWithProviders(<Harness />);
    await userEvent.click(screen.getByRole("combobox", { name: "Icon" }));
    await userEvent.type(screen.getByLabelText(/search icons/i), "zzzzz");
    expect(await screen.findByText(/no matching icons/i)).toBeInTheDocument();
  });

  it("clears the selected icon", async () => {
    renderWithProviders(<Harness initial="wifi" />);
    await userEvent.click(screen.getByRole("combobox", { name: "Icon" }));
    await userEvent.click(screen.getByRole("button", { name: /clear icon/i }));
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("(empty)"));
  });
});
