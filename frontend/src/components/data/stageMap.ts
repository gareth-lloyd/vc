export type StageTone = "neutral" | "active" | "complete" | "failed";

export interface StageInfo {
  filled: number;
  tone: StageTone;
}

export const STAGE_TOTAL_PIPS = 5;

const STAGE_MAP: Record<string, StageInfo> = {
  draft: { filled: 0, tone: "neutral" },
  pending_owner_approval: { filled: 1, tone: "active" },
  awaiting_deposit: { filled: 2, tone: "active" },
  deposit_paid: { filled: 3, tone: "active" },
  awaiting_balance: { filled: 3, tone: "active" },
  balance_paid: { filled: 4, tone: "active" },
  checked_in: { filled: 5, tone: "active" },
  checked_out: { filled: 5, tone: "complete" },
  cancelled: { filled: 0, tone: "failed" },
  expired: { filled: 0, tone: "failed" },
  declined: { filled: 0, tone: "failed" },
};

export function stageForStatus(status: string): StageInfo {
  return STAGE_MAP[status] ?? { filled: 0, tone: "neutral" };
}
