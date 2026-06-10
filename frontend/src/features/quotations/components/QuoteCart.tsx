import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { isStagedLineValid } from "../lineTotals";
import type { StagedLine } from "../schemas";
import { QuoteCartLine } from "./QuoteCartLine";

interface Props {
  lines: StagedLine[];
  onUpdateLine: (propertyId: number, patch: Partial<StagedLine>) => void;
  onRemove: (propertyId: number) => void;
  onSaveDraft: () => void;
  onSendToGuest: () => void;
}

export function QuoteCart({ lines, onUpdateLine, onRemove, onSaveDraft, onSendToGuest }: Props) {
  const { t } = useTranslation("quotations");
  const hasRole = useHasReservationsRole();
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Auto-expand a no-rate manual line exactly once, when it is first staged,
  // so the operator lands on the total/reason inputs they must fill. Track
  // seen ids in a ref — keying off `lines` alone would re-expand a line the
  // user has deliberately collapsed on every later edit.
  const seenIds = useRef<Set<number>>(new Set());
  useEffect(() => {
    // Prune removed lines first, so a removed-then-re-staged villa counts as
    // a fresh add and auto-expands again.
    const current = new Set(lines.map((line) => line.property_id));
    for (const id of seenIds.current) {
      if (!current.has(id)) seenIds.current.delete(id);
    }
    for (const line of lines) {
      if (seenIds.current.has(line.property_id)) continue;
      seenIds.current.add(line.property_id);
      if (line.is_manual && line.total == null) setExpandedId(line.property_id);
    }
  }, [lines]);

  const anyInvalid = lines.some((line) => !isStagedLineValid(line));

  // Why the actions are blocked, most-blocking first. `null` ⇒ enabled.
  const disableReason = (): string | null => {
    if (!hasRole) return t("common:errors.reservations_role_required");
    if (lines.length === 0) return t("builder.cart.disable_reasons.no_lines");
    if (anyInvalid) return t("builder.cart.disable_reasons.invalid_line");
    return null;
  };
  const reason = disableReason();
  const disabled = reason != null;

  return (
    <div className="border-border bg-card flex flex-col gap-4 rounded-lg border p-4">
      <h2 className="text-foreground text-lg font-semibold">
        {t("builder.cart.heading", { count: lines.length })}
      </h2>

      {lines.length === 0 ? (
        <EmptyState
          title={t("builder.cart.empty.title")}
          description={t("builder.cart.empty.description")}
        />
      ) : (
        <div className="space-y-3">
          {lines.map((line) => (
            <QuoteCartLine
              key={line.property_id}
              line={line}
              expanded={expandedId === line.property_id}
              onToggle={() =>
                setExpandedId((id) => (id === line.property_id ? null : line.property_id))
              }
              onUpdate={(patch) => onUpdateLine(line.property_id, patch)}
              onRemove={() => onRemove(line.property_id)}
            />
          ))}
        </div>
      )}

      <CartActions
        reason={reason}
        disabled={disabled}
        onSaveDraft={onSaveDraft}
        onSendToGuest={onSendToGuest}
      />
    </div>
  );
}

interface CartActionsProps {
  reason: string | null;
  disabled: boolean;
  onSaveDraft: () => void;
  onSendToGuest: () => void;
}

// The two commit affordances, wrapped in a single tooltip when blocked so the
// operator learns why (no role / no lines / an invalid manual override).
function CartActions({ reason, disabled, onSaveDraft, onSendToGuest }: CartActionsProps) {
  const { t } = useTranslation("quotations");
  const buttons = (
    <div className="flex flex-col gap-2">
      <Button type="button" disabled={disabled} onClick={onSendToGuest}>
        {t("builder.cart.send_to_guest")}
      </Button>
      <Button type="button" variant="outline" disabled={disabled} onClick={onSaveDraft}>
        {t("builder.cart.save_draft")}
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
