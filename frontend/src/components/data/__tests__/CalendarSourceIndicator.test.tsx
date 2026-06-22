import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { CalendarSourceIndicator } from "../CalendarSourceIndicator";

const ONLINE_LABEL = "Online calendar";

describe("CalendarSourceIndicator", () => {
  it("shows the iCal badge when the property has an active feed", () => {
    renderWithProviders(<CalendarSourceIndicator hasActiveIcalFeed />);
    expect(screen.getByText("iCal")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows an external link when there is a calendar_url but no active feed", () => {
    const url = "https://owner.example.com/calendar";
    renderWithProviders(<CalendarSourceIndicator hasActiveIcalFeed={false} calendarUrl={url} />);
    const link = screen.getByRole("link", { name: ONLINE_LABEL });
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(screen.queryByText("iCal")).not.toBeInTheDocument();
  });

  it("renders nothing when there is neither a feed nor a calendar_url", () => {
    const { container } = renderWithProviders(
      <CalendarSourceIndicator hasActiveIcalFeed={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("prefers the iCal badge when the property has both a feed and a calendar_url", () => {
    renderWithProviders(
      <CalendarSourceIndicator
        hasActiveIcalFeed
        calendarUrl="https://owner.example.com/calendar"
      />,
    );
    expect(screen.getByText("iCal")).toBeInTheDocument();
    // Badge wins → the link is suppressed.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
