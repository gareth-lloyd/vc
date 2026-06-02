import { cva } from "class-variance-authority";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { STAGE_TOTAL_PIPS, stageForStatus } from "./stageMap";

const pipVariants = cva("h-1.5 w-4 rounded-full", {
  variants: {
    fill: {
      muted: "bg-muted",
      neutral: "bg-muted-foreground",
      active: "bg-foreground",
      complete: "bg-success",
      failed: "bg-destructive",
    },
  },
  defaultVariants: {
    fill: "muted",
  },
});

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
            className={pipVariants({ fill: isFilled ? tone : "muted" })}
          />
        );
      })}
    </div>
  );
}
