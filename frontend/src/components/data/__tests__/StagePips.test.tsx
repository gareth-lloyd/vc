import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { StagePips } from "../StagePips";
import { stageForStatus } from "../stageMap";

describe("stageForStatus", () => {
  it("maps progressive statuses to increasing pip counts", () => {
    expect(stageForStatus("draft").filled).toBe(0);
    expect(stageForStatus("pending_owner_approval").filled).toBe(1);
    expect(stageForStatus("awaiting_deposit").filled).toBe(2);
    expect(stageForStatus("deposit_paid").filled).toBe(3);
    expect(stageForStatus("awaiting_balance").filled).toBe(3);
    expect(stageForStatus("balance_paid").filled).toBe(4);
    expect(stageForStatus("checked_in").filled).toBe(5);
    expect(stageForStatus("checked_out").filled).toBe(5);
  });

  it("marks terminal-negative statuses as failed (0 filled)", () => {
    expect(stageForStatus("cancelled").tone).toBe("failed");
    expect(stageForStatus("expired").tone).toBe("failed");
    expect(stageForStatus("declined").tone).toBe("failed");
    expect(stageForStatus("cancelled").filled).toBe(0);
  });

  it("returns a safe default for unknown statuses", () => {
    expect(stageForStatus("unknown_made_up").filled).toBe(0);
    expect(stageForStatus("unknown_made_up").tone).toBe("neutral");
  });
});

describe("StagePips", () => {
  it("renders 5 pips", () => {
    const { container } = render(<StagePips status="deposit_paid" />);
    const pips = container.querySelectorAll('[data-pip="true"]');
    expect(pips).toHaveLength(5);
  });

  it("marks the right number as filled", () => {
    const { container } = render(<StagePips status="deposit_paid" />);
    const filled = container.querySelectorAll('[data-pip-filled="true"]');
    expect(filled).toHaveLength(3);
  });
});
