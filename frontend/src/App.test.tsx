import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the Villa Collective heading", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { level: 1, name: /villa collective/i }),
    ).toBeInTheDocument();
  });
});
