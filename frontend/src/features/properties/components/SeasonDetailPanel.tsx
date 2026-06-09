import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import {
  useDeleteRateCard,
  useDeleteRateRule,
  useDuplicateRateCard,
  useSeasonDetail,
} from "../hooks";
import { RateCardFormDialog } from "./RateCardFormDialog";
import { RateRuleFormDialog } from "./RateRuleFormDialog";
import type { RateCard, RateRule, RateRuleWriteInput } from "../schemas";

export function ActiveBadge({ isActive }: { isActive: boolean | undefined }) {
  const { t } = useTranslation("properties");
  return isActive ? (
    <Badge variant="secondary">{t("pricing.active_badge")}</Badge>
  ) : (
    <Badge variant="outline">{t("pricing.inactive_badge")}</Badge>
  );
}

/** Seed the next rule from the card's latest date band for fast consecutive entry. */
function nextRuleDefaults(card: RateCard): Partial<RateRuleWriteInput> | undefined {
  const last = card.rules.reduce<RateRule | null>(
    (latest, rule) => (latest === null || rule.date_to > latest.date_to ? rule : latest),
    null,
  );
  if (!last) return undefined;
  return {
    date_from: last.date_to,
    min_party: last.min_party ?? 1,
    max_party: last.max_party ?? 1,
  };
}

function RateCardBlock({
  card,
  canWrite,
  onEdit,
  onDuplicate,
  onDelete,
  onAddRule,
  onEditRule,
  onDeleteRule,
}: {
  card: RateCard;
  canWrite: boolean;
  onEdit: (card: RateCard) => void;
  onDuplicate: (card: RateCard) => void;
  onDelete: (card: RateCard) => void;
  onAddRule: (card: RateCard) => void;
  onEditRule: (rule: RateRule) => void;
  onDeleteRule: (rule: RateRule) => void;
}) {
  const { t } = useTranslation("properties");
  const poa = t("pricing.rate_card.poa");
  const dash = t("common.unset");
  const placeholder = t("pricing.rate_card.nights_min_placeholder");
  return (
    <div className="border-border bg-card space-y-3 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h4 className="text-foreground text-sm font-semibold">{card.name}</h4>
          {card.description ? (
            <p className="text-muted-foreground text-xs">{card.description}</p>
          ) : null}
          <p className="text-muted-foreground mt-1 text-xs">
            {card.min_nights != null || card.max_nights != null
              ? t("pricing.rate_card.nights_range", {
                  min: card.min_nights ?? placeholder,
                  max: card.max_nights ?? placeholder,
                })
              : t("pricing.rate_card.any_length")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ActiveBadge isActive={card.is_active} />
          {canWrite ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  aria-label={t("pricing.rate_card.row.menu_label")}
                >
                  ···
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onEdit(card)}>
                  {t("pricing.rate_card.row.edit")}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onDuplicate(card)}>
                  {t("pricing.rate_card.row.duplicate")}
                </DropdownMenuItem>
                <DropdownMenuItem className="text-destructive" onClick={() => onDelete(card)}>
                  {t("pricing.rate_card.row.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>
      {card.rules.length === 0 ? (
        <p className="text-muted-foreground text-xs italic">{t("pricing.rate_card.no_rules")}</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-muted-foreground text-left">
            <tr>
              <th className="py-1 pr-2 font-medium">{t("pricing.rules_table.dates")}</th>
              <th className="py-1 pr-2 font-medium">{t("pricing.rules_table.party")}</th>
              <th className="py-1 pr-2 font-medium">{t("pricing.rules_table.nightly")}</th>
              <th className="py-1 font-medium">{t("pricing.rules_table.weekly")}</th>
              {canWrite ? (
                <th className="py-1 text-right font-medium">
                  <span className="sr-only">{t("pricing.rules_table.actions")}</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {card.rules.map((rule) => (
              <tr key={rule.id} className="border-border border-t">
                <td className="py-1 pr-2">
                  {formatDate(rule.date_from)} – {formatDate(rule.date_to)}
                </td>
                <td className="py-1 pr-2">
                  {rule.min_party ?? placeholder}–{rule.max_party ?? placeholder}
                </td>
                <td className="py-1 pr-2">{rule.is_poa ? poa : (rule.nightly ?? dash)}</td>
                <td className="py-1">{rule.is_poa ? poa : (rule.weekly ?? dash)}</td>
                {canWrite ? (
                  <td className="py-1 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2"
                          aria-label={t("pricing.rule.row.menu_label")}
                        >
                          ···
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onEditRule(rule)}>
                          {t("pricing.rule.row.edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => onDeleteRule(rule)}
                        >
                          {t("pricing.rule.row.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canWrite ? (
        <Button variant="ghost" size="sm" onClick={() => onAddRule(card)}>
          {t("pricing.rule.add_button")}
        </Button>
      ) : null}
    </div>
  );
}

export function SeasonDetailPanel({
  seasonId,
  onBack,
  canWrite,
}: {
  seasonId: number;
  onBack: () => void;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const detail = useSeasonDetail(seasonId);
  const dash = t("common.unset");

  const deleteCardMutation = useDeleteRateCard(seasonId);
  const duplicateCardMutation = useDuplicateRateCard(seasonId);
  const deleteRuleMutation = useDeleteRateRule(seasonId);

  const [addCardOpen, setAddCardOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<RateCard | null>(null);
  const [duplicatingCard, setDuplicatingCard] = useState<RateCard | null>(null);
  const [deletingCard, setDeletingCard] = useState<RateCard | null>(null);
  const [addingRuleCard, setAddingRuleCard] = useState<RateCard | null>(null);
  const [editingRule, setEditingRule] = useState<RateRule | null>(null);
  const [deletingRule, setDeletingRule] = useState<RateRule | null>(null);

  const handleDeleteCard = async () => {
    if (!deletingCard) return;
    try {
      await deleteCardMutation.mutateAsync({ cardId: deletingCard.id });
      toast.success(t("pricing.rate_card.toasts.deleted"));
      setDeletingCard(null);
    } catch {
      toast.error(t("pricing.rate_card.toasts.delete_failed"));
    }
  };

  const handleDuplicateCard = async () => {
    if (!duplicatingCard) return;
    try {
      await duplicateCardMutation.mutateAsync({ cardId: duplicatingCard.id });
      toast.success(t("pricing.rate_card.toasts.duplicated"));
      setDuplicatingCard(null);
    } catch {
      toast.error(t("pricing.rate_card.toasts.duplicate_failed"));
    }
  };

  const handleDeleteRule = async () => {
    if (!deletingRule) return;
    try {
      await deleteRuleMutation.mutateAsync({ ruleId: deletingRule.id });
      toast.success(t("pricing.rule.toasts.deleted"));
      setDeletingRule(null);
    } catch {
      toast.error(t("pricing.rule.toasts.delete_failed"));
    }
  };

  const addCardButton = canWrite ? (
    <Button size="sm" onClick={() => setAddCardOpen(true)}>
      {t("pricing.rate_card.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("pricing.rate_card.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("pricing.rate_card.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}>
        {t("pricing.season_detail.back")}
      </Button>
      {detail.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : detail.isError || !detail.data ? (
        <ErrorState
          title={t("pricing.season_detail.error_title")}
          description={t("pricing.season_detail.error_body")}
          onRetry={() => detail.refetch()}
        />
      ) : (
        <>
          <FactList>
            <FactRow label={t("pricing.season_detail.fields.name")} value={detail.data.name} />
            <FactRow
              label={t("pricing.season_detail.fields.currency")}
              value={detail.data.currency_code ?? dash}
            />
            <FactRow
              label={t("pricing.season_detail.fields.price_basis")}
              value={detail.data.price_basis ?? dash}
            />
            <FactRow
              label={t("pricing.season_detail.fields.effective")}
              value={`${formatDate(detail.data.effective_from)} – ${formatDate(detail.data.effective_to)}`}
            />
            <FactRow
              label={t("pricing.season_detail.fields.status")}
              value={<ActiveBadge isActive={detail.data.is_active} />}
            />
          </FactList>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-foreground text-sm font-semibold">
                {t("pricing.season_detail.rate_cards_heading")}
              </h3>
              {addCardButton}
            </div>
            {detail.data.cards.length === 0 ? (
              <EmptyState title={t("pricing.season_detail.empty_rate_cards")} />
            ) : (
              detail.data.cards.map((card) => (
                <RateCardBlock
                  key={card.id}
                  card={card}
                  canWrite={canWrite}
                  onEdit={setEditingCard}
                  onDuplicate={setDuplicatingCard}
                  onDelete={setDeletingCard}
                  onAddRule={setAddingRuleCard}
                  onEditRule={setEditingRule}
                  onDeleteRule={setDeletingRule}
                />
              ))
            )}
          </div>
        </>
      )}

      {addCardOpen ? (
        <RateCardFormDialog
          seasonId={seasonId}
          open={addCardOpen}
          onOpenChange={setAddCardOpen}
          mode="create"
        />
      ) : null}
      {editingCard ? (
        <RateCardFormDialog
          seasonId={seasonId}
          open={!!editingCard}
          onOpenChange={(o) => !o && setEditingCard(null)}
          mode="edit"
          card={editingCard}
        />
      ) : null}
      {addingRuleCard ? (
        <RateRuleFormDialog
          seasonId={seasonId}
          cardId={addingRuleCard.id}
          open={!!addingRuleCard}
          onOpenChange={(o) => !o && setAddingRuleCard(null)}
          mode="create"
          defaults={nextRuleDefaults(addingRuleCard)}
        />
      ) : null}
      {editingRule ? (
        <RateRuleFormDialog
          seasonId={seasonId}
          cardId={editingRule.card}
          open={!!editingRule}
          onOpenChange={(o) => !o && setEditingRule(null)}
          mode="edit"
          rule={editingRule}
        />
      ) : null}
      {deletingCard ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingCard(null)}
          onConfirm={handleDeleteCard}
          title={t("pricing.rate_card.delete_confirm.title")}
          description={t("pricing.rate_card.delete_confirm.description")}
          confirmLabel={t("pricing.rate_card.delete_confirm.confirm")}
          destructive
          busy={deleteCardMutation.isPending}
        />
      ) : null}
      {duplicatingCard ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDuplicatingCard(null)}
          onConfirm={handleDuplicateCard}
          title={t("pricing.rate_card.duplicate_confirm.title")}
          description={t("pricing.rate_card.duplicate_confirm.description")}
          confirmLabel={t("pricing.rate_card.duplicate_confirm.confirm")}
          busy={duplicateCardMutation.isPending}
        />
      ) : null}
      {deletingRule ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingRule(null)}
          onConfirm={handleDeleteRule}
          title={t("pricing.rule.delete_confirm.title")}
          description={t("pricing.rule.delete_confirm.description")}
          confirmLabel={t("pricing.rule.delete_confirm.confirm")}
          destructive
          busy={deleteRuleMutation.isPending}
        />
      ) : null}
    </div>
  );
}
