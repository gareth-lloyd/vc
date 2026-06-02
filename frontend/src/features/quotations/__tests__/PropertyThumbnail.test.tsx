import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PropertyThumbnail } from "../components/PropertyThumbnail";

describe("PropertyThumbnail", () => {
  it("renders an image with alt text when a src is present", () => {
    render(
      <PropertyThumbnail
        src="https://cdn.example/villa.jpg"
        fallbackText="Villa Sol"
        alt="Villa Sol thumbnail"
      />,
    );
    const img = screen.getByAltText("Villa Sol thumbnail") as HTMLImageElement;
    expect(img.src).toContain("villa.jpg");
  });

  it("falls back to the property initial when there is no image", () => {
    render(<PropertyThumbnail src={null} fallbackText="Villa Sol" alt="Villa Sol thumbnail" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("V")).toBeInTheDocument();
  });

  it("shows a dash when neither image nor fallback text is available", () => {
    render(<PropertyThumbnail src={undefined} fallbackText={null} alt="thumbnail" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
