import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FormErrorAlert } from "../FormErrorAlert";

describe("FormErrorAlert", () => {
  it("renders nothing when there is no message and no field errors", () => {
    const { container } = render(<FormErrorAlert message={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders just the message when no field errors are given (backward compatible)", () => {
    render(<FormErrorAlert message="Validation failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Validation failed");
  });

  it("lists each field-error message beneath the detail message", () => {
    render(
      <FormErrorAlert
        message="Validation failed"
        fieldErrors={{
          min_nights_rental_note: { type: "server", message: "This field may not be null." },
          check_in_time: { type: "server", message: "Enter a valid time." },
        }}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Validation failed");
    expect(screen.getByText("This field may not be null.")).toBeInTheDocument();
    expect(screen.getByText("Enter a valid time.")).toBeInTheDocument();
  });

  it("renders field errors even when there is no top-level message", () => {
    render(
      <FormErrorAlert
        message={null}
        fieldErrors={{
          min_nights_rental_note: { type: "server", message: "This field may not be null." },
        }}
      />,
    );
    expect(screen.getByText("This field may not be null.")).toBeInTheDocument();
  });

  it("ignores field-error entries that carry no string message", () => {
    render(<FormErrorAlert message={null} fieldErrors={{ foo: undefined, bar: { type: "x" } }} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
