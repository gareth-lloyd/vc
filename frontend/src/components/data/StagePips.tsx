import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { STAGE_TOTAL_PIPS, stageForStatus, type StageTone } from "./stageMap";

const TONE_FILLED: Record<StageTone, string> = {
  neutral: "bg-muted-foreground",
  active: "bg-foreground",
  complete: "bg-emerald-600",
  failed: "bg-destructive",
};

export function StagePips({ status, className }: { status: string; className?: string }) {
  const { t } = useTranslation();
  const { filled, tone } = stageForStatus(status);
  return (
    <div
      className={cn("flex items-center gap-1", className)}
      aria-label={t("aria.stage", { status })}
    >
      {Array.from({ length: STAGE_TOTAL_PIPS }, (_, i) => {
        const isFilled = i < filled;
        return (
          <span
            key={i}
            data-pip="true"
            data-pip-filled={isFilled ? "true" : "false"}
            className={cn("h-1.5 w-4 rounded-full", isFilled ? TONE_FILLED[tone] : "bg-muted")}
          />
        );
      })}
    </div>
  );
}
