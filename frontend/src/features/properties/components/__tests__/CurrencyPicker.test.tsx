import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { CurrencyPicker } from "../CurrencyPicker";

const eur = { id: 42, code: "EUR", name: "Euro", symbol: "€", decimal_places: 2, is_active: true };
const gbp = {
  id: 43,
  code: "GBP",
  name: "British Pound",
  symbol: "£",
  decimal_places: 2,
  is_active: true,
};
// An inactive currency must never be offered by the picker.
const usd = {
  id: 44,
  code: "USD",
  name: "US Dollar",
  symbol: "$",
  decimal_places: 2,
  is_active: false,
};

function installCurrencies() {
  server.use(http.get("/api/v1/currencies", () => HttpResponse.json(drfPage([eur, gbp, usd]))));
}

describe("CurrencyPicker", () => {
  it("lists only active currencies and emits the id on selection", async () => {
    installCurrencies();
    const onChange = vi.fn();
    renderWithProviders(<CurrencyPicker value={null} onChange={onChange} placeholder="Pick one" />);

    const trigger = screen.getByRole("combobox");
    await waitFor(() => expect(trigger).not.toBeDisabled());
    await userEvent.click(trigger);

    // Inactive USD is filtered out; active currencies are offered.
    expect(screen.queryByRole("option", { name: /US Dollar/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: /British Pound/ }));

    expect(onChange).toHaveBeenCalledWith(43);
  });

  it("without allowUnset shows the placeholder and offers no unset item", async () => {
    installCurrencies();
    renderWithProviders(<CurrencyPicker value={null} onChange={vi.fn()} placeholder="Pick one" />);

    const trigger = screen.getByRole("combobox");
    expect(trigger).toHaveTextContent("Pick one");
    await waitFor(() => expect(trigger).not.toBeDisabled());
    await userEvent.click(trigger);
    expect(screen.queryByRole("option", { name: "No value" })).not.toBeInTheDocument();
  });

  it("with allowUnset shows the unset item as selected for a null value", async () => {
    installCurrencies();
    renderWithProviders(
      <CurrencyPicker
        value={null}
        onChange={vi.fn()}
        allowUnset
        unsetLabel="No value"
        onUnset={vi.fn()}
      />,
    );

    // A null value maps to the sentinel, so the unset label shows selected.
    expect(screen.getByRole("combobox")).toHaveTextContent("No value");
  });

  it("with allowUnset emits onUnset when the unset item is chosen", async () => {
    installCurrencies();
    const onUnset = vi.fn();
    const onChange = vi.fn();
    renderWithProviders(
      <CurrencyPicker
        value={43}
        onChange={onChange}
        allowUnset
        unsetLabel="No value"
        onUnset={onUnset}
      />,
    );

    const trigger = screen.getByRole("combobox");
    await waitFor(() => expect(trigger).not.toBeDisabled());
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("option", { name: "No value" }));

    expect(onUnset).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });
});
