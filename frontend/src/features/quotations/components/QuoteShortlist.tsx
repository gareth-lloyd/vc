import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { isStagedLineValid } from "../lineTotals";
import type { StagedLine } from "../schemas";
import { QuoteShortlistLine } from "./QuoteShortlistLine";

interface Props {
  lines: StagedLine[];
  onUpdateLine: (lineId: string, patch: Partial<StagedLine>) => void;
  onRemove: (lineId: string) => void;
  onSaveDraft: () => void;
  onSendToGuest: () => void;
}

export function QuoteShortlist({
  lines,
  onUpdateLine,
  onRemove,
  onSaveDraft,
  onSendToGuest,
}: Props) {
  const { t } = useTranslation("quotations");
  const hasRole = useHasReservationsRole();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Auto-expand a no-rate manual line exactly once, when it is first staged,
  // so the operator lands on the total/reason inputs they must fill. Track
  // seen ids in a ref — keying off `lines` alone would re-expand a line the
  // user has deliberately collapsed on every later edit.
  const seenIds = useRef<Set<string>>(new Set());
  useEffect(() => {
    // Prune removed lines first, so a removed-then-re-staged week counts as
    // a fresh add and auto-expands again.
    const current = new Set(lines.map((line) => line.line_id));
    for (const id of seenIds.current) {
      if (!current.has(id)) seenIds.current.delete(id);
    }
    for (const line of lines) {
      if (seenIds.current.has(line.line_id)) continue;
      seenIds.current.add(line.line_id);
      if (line.is_manual && line.total == null) setExpandedId(line.line_id);
    }
  }, [lines]);

  const anyInvalid = lines.some((line) => !isStagedLineValid(line));

  // Why the actions are blocked, most-blocking first. `null` ⇒ enabled.
  const disableReason = (): string | null => {
    if (!hasRole) return t("common:errors.reservations_role_required");
    if (lines.length === 0) return t("builder.shortlist.disable_reasons.no_lines");
    if (anyInvalid) return t("builder.shortlist.disable_reasons.invalid_line");
    return null;
  };
  const reason = disableReason();
  const disabled = reason != null;

  return (
    <div className="border-border bg-card flex flex-col gap-4 rounded-lg border p-4">
      <h2 className="text-foreground text-lg font-semibold">
        {t("builder.shortlist.heading", { count: lines.length })}
      </h2>

      {lines.length === 0 ? (
        <EmptyState
          title={t("builder.shortlist.empty.title")}
          description={t("builder.shortlist.empty.description")}
        />
      ) : (
        <div className="space-y-3">
          {lines.map((line) => (
            <QuoteShortlistLine
              key={line.line_id}
              line={line}
              expanded={expandedId === line.line_id}
              onToggle={() => setExpandedId((id) => (id === line.line_id ? null : line.line_id))}
              onUpdate={(patch) => onUpdateLine(line.line_id, patch)}
              onRemove={() => onRemove(line.line_id)}
            />
          ))}
        </div>
      )}

      <ShortlistActions
        reason={reason}
        disabled={disabled}
        onSaveDraft={onSaveDraft}
        onSendToGuest={onSendToGuest}
      />
    </div>
  );
}

interface ShortlistActionsProps {
  reason: string | null;
  disabled: boolean;
  onSaveDraft: () => void;
  onSendToGuest: () => void;
}

// The two commit affordances, wrapped in a single tooltip when blocked so the
// operator learns why (no role / no lines / an invalid manual override).
function ShortlistActions({ reason, disabled, onSaveDraft, onSendToGuest }: ShortlistActionsProps) {
  const { t } = useTranslation("quotations");
  const buttons = (
    <div className="flex flex-col gap-2">
      <Button type="button" disabled={disabled} onClick={onSendToGuest}>
        {t("builder.shortlist.send_to_guest")}
      </Button>
      <Button type="button" variant="outline" disabled={disabled} onClick={onSaveDraft}>
        {t("builder.shortlist.save_draft")}
      </Button>
    </div>
  );
  if (reason == null) return buttons;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block">{buttons}</span>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  );
}
