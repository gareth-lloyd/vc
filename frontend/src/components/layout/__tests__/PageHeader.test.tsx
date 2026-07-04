import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { PageHeader } from "../PageHeader";

describe("PageHeader", () => {
  beforeEach(() => {
    document.title = "seed";
  });

  it("sets the browser tab title from its title prop", () => {
    render(<PageHeader title="Bookings" />);
    expect(document.title).toBe("Bookings · Villa Collective");
  });
});
