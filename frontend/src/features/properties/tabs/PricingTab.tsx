import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
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
import { Section } from "@/components/data/Section";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { SeasonFormDialog } from "../components/SeasonFormDialog";
import {
  useDeleteSeason,
  useDuplicateSeason,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertySeasons,
  useSeasonDetail,
} from "../hooks";
import type { Discount, Extra, PropertyDetail, RateCard, RatePlan } from "../schemas";

interface PricingContext {
  property: PropertyDetail;
}

function ActiveBadge({ isActive }: { isActive: boolean | undefined }) {
  const { t } = useTranslation("properties");
  return isActive ? (
    <Badge variant="secondary">{t("pricing.active_badge")}</Badge>
  ) : (
    <Badge variant="outline">{t("pricing.inactive_badge")}</Badge>
  );
}

function SeasonsList({
  seasons,
  onSelect,
  canWrite,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  seasons: RatePlan[];
  onSelect: (seasonId: number) => void;
  canWrite: boolean;
  onEdit: (season: RatePlan) => void;
  onDuplicate: (season: RatePlan) => void;
  onDelete: (season: RatePlan) => void;
}) {
  const { t } = useTranslation("properties");
  if (seasons.length === 0) {
    return <EmptyState title={t("pricing.seasons.empty")} />;
  }
  return (
    <ul className="border-border bg-card divide-border divide-y rounded-lg border">
      {seasons.map((plan) => (
        <li key={plan.id} className="flex items-center gap-2 pr-2">
          <button
            type="button"
            onClick={() => onSelect(plan.id)}
            className="hover:bg-accent flex flex-1 items-center justify-between px-4 py-3 text-left text-sm"
          >
            <span className="flex flex-col">
              <span className="text-foreground font-medium">{plan.name}</span>
              <span className="text-muted-foreground text-xs">
                {formatDate(plan.effective_from)} – {formatDate(plan.effective_to)}
                {plan.currency ? ` · ${plan.currency}` : ""}
              </span>
            </span>
            <ActiveBadge isActive={plan.is_active} />
          </button>
          {canWrite ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  aria-label={t("pricing.seasons.row.menu_label")}
                >
                  ···
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onEdit(plan)}>
                  {t("pricing.seasons.row.edit")}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onDuplicate(plan)}>
                  {t("pricing.seasons.row.duplicate")}
                </DropdownMenuItem>
                <DropdownMenuItem className="text-destructive" onClick={() => onDelete(plan)}>
                  {t("pricing.seasons.row.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function RateCardBlock({ card }: { card: RateCard }) {
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
            {card.changeover_weekday != null
              ? t("pricing.rate_card.changeover_weekday", { weekday: card.changeover_weekday })
              : ""}
          </p>
        </div>
        <ActiveBadge isActive={card.is_active} />
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
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SeasonDetailPanel({ seasonId, onBack }: { seasonId: number; onBack: () => void }) {
  const { t } = useTranslation("properties");
  const detail = useSeasonDetail(seasonId);
  const dash = t("common.unset");
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
              value={detail.data.currency ?? dash}
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
            <h3 className="text-foreground text-sm font-semibold">
              {t("pricing.season_detail.rate_cards_heading")}
            </h3>
            {detail.data.cards.length === 0 ? (
              <EmptyState title={t("pricing.season_detail.empty_rate_cards")} />
            ) : (
              detail.data.cards.map((card) => <RateCardBlock key={card.id} card={card} />)
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ExtrasTable({ extras }: { extras: Extra[] }) {
  const { t } = useTranslation("properties");
  const dash = t("common.unset");
  if (extras.length === 0) {
    return <EmptyState title={t("pricing.extras.empty")} />;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground text-left text-xs">
        <tr>
          <th className="py-2 pr-2 font-medium">{t("pricing.extras_table.name")}</th>
          <th className="py-2 pr-2 font-medium">{t("pricing.extras_table.kind")}</th>
          <th className="py-2 pr-2 font-medium">{t("pricing.extras_table.amount")}</th>
          <th className="py-2 font-medium">{t("pricing.extras_table.mandatory")}</th>
        </tr>
      </thead>
      <tbody>
        {extras.map((extra) => (
          <tr key={extra.id} className="border-border border-t">
            <td className="py-2 pr-2">{extra.name}</td>
            <td className="text-muted-foreground py-2 pr-2">{extra.kind ?? dash}</td>
            <td className="py-2 pr-2">{formatMoney(extra.amount, extra.currency ?? null)}</td>
            <td className="py-2">
              {extra.is_mandatory
                ? t("pricing.extras_table.mandatory_yes")
                : t("pricing.extras_table.mandatory_no")}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DiscountsTable({ discounts }: { discounts: Discount[] }) {
  const { t } = useTranslation("properties");
  const dash = t("common.unset");
  if (discounts.length === 0) {
    return <EmptyState title={t("pricing.discounts.empty")} />;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground text-left text-xs">
        <tr>
          <th className="py-2 pr-2 font-medium">{t("pricing.discounts_table.name")}</th>
          <th className="py-2 pr-2 font-medium">{t("pricing.discounts_table.code")}</th>
          <th className="py-2 pr-2 font-medium">{t("pricing.discounts_table.kind")}</th>
          <th className="py-2 pr-2 font-medium">{t("pricing.discounts_table.amount")}</th>
          <th className="py-2 font-medium">{t("pricing.discounts_table.valid")}</th>
        </tr>
      </thead>
      <tbody>
        {discounts.map((d) => (
          <tr key={d.id} className="border-border border-t">
            <td className="py-2 pr-2">{d.name}</td>
            <td className="text-muted-foreground py-2 pr-2 font-mono text-xs">{d.code ?? dash}</td>
            <td className="text-muted-foreground py-2 pr-2">{d.kind ?? dash}</td>
            <td className="py-2 pr-2">{d.amount ?? dash}</td>
            <td className="text-muted-foreground py-2">
              {formatDate(d.valid_from)} – {formatDate(d.valid_to)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PricingTab() {
  const { t } = useTranslation("properties");
  const { property } = useOutletContext<PricingContext>();
  const seasons = usePropertySeasons(property.id);
  const extras = usePropertyExtras(property.id);
  const discounts = usePropertyDiscounts(property.id);
  const canWrite = useHasReservationsRole();
  const deleteSeasonMutation = useDeleteSeason(property.id);
  const duplicateSeasonMutation = useDuplicateSeason(property.id);
  const [selectedSeasonId, setSelectedSeasonId] = useState<number | null>(null);
  const [addSeasonOpen, setAddSeasonOpen] = useState(false);
  const [editingSeason, setEditingSeason] = useState<RatePlan | null>(null);
  const [deletingSeason, setDeletingSeason] = useState<RatePlan | null>(null);
  const [duplicatingSeason, setDuplicatingSeason] = useState<RatePlan | null>(null);

  const handleDeleteSeason = async () => {
    if (!deletingSeason) return;
    try {
      await deleteSeasonMutation.mutateAsync({ seasonId: deletingSeason.id });
      toast.success(t("pricing.seasons.toasts.deleted"));
      setDeletingSeason(null);
    } catch {
      toast.error(t("pricing.seasons.toasts.delete_failed"));
    }
  };

  const handleDuplicateSeason = async () => {
    if (!duplicatingSeason) return;
    try {
      await duplicateSeasonMutation.mutateAsync({ seasonId: duplicatingSeason.id });
      toast.success(t("pricing.seasons.toasts.duplicated"));
      setDuplicatingSeason(null);
    } catch {
      toast.error(t("pricing.seasons.toasts.duplicate_failed"));
    }
  };

  const addSeasonButton = canWrite ? (
    <Button size="sm" onClick={() => setAddSeasonOpen(true)}>
      {t("pricing.seasons.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("pricing.seasons.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("pricing.seasons.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-8 p-6">
      <Section
        title={t("pricing.sections.seasons")}
        actions={selectedSeasonId == null ? addSeasonButton : null}
      >
        {seasons.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : seasons.isError ? (
          <ErrorState
            title={t("pricing.seasons.error_title")}
            description={t("pricing.seasons.error_body")}
            onRetry={() => seasons.refetch()}
          />
        ) : selectedSeasonId != null ? (
          <SeasonDetailPanel seasonId={selectedSeasonId} onBack={() => setSelectedSeasonId(null)} />
        ) : (
          <SeasonsList
            seasons={seasons.data?.results ?? []}
            onSelect={setSelectedSeasonId}
            canWrite={canWrite}
            onEdit={setEditingSeason}
            onDuplicate={setDuplicatingSeason}
            onDelete={setDeletingSeason}
          />
        )}
      </Section>

      <Section title={t("pricing.sections.extras")}>
        {extras.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : extras.isError ? (
          <ErrorState
            title={t("pricing.extras.error_title")}
            description={t("pricing.extras.error_body")}
            onRetry={() => extras.refetch()}
          />
        ) : (
          <ExtrasTable extras={extras.data?.results ?? []} />
        )}
      </Section>

      <Section title={t("pricing.sections.discounts")}>
        {discounts.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : discounts.isError ? (
          <ErrorState
            title={t("pricing.discounts.error_title")}
            description={t("pricing.discounts.error_body")}
            onRetry={() => discounts.refetch()}
          />
        ) : (
          <DiscountsTable discounts={discounts.data?.results ?? []} />
        )}
      </Section>

      {addSeasonOpen ? (
        <SeasonFormDialog
          propertyId={property.id}
          open={addSeasonOpen}
          onOpenChange={setAddSeasonOpen}
          mode="create"
        />
      ) : null}
      {editingSeason ? (
        <SeasonFormDialog
          propertyId={property.id}
          open={!!editingSeason}
          onOpenChange={(o) => !o && setEditingSeason(null)}
          mode="edit"
          season={editingSeason}
        />
      ) : null}
      {deletingSeason ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingSeason(null)}
          onConfirm={handleDeleteSeason}
          title={t("pricing.seasons.delete_confirm.title")}
          description={t("pricing.seasons.delete_confirm.description")}
          confirmLabel={t("pricing.seasons.delete_confirm.confirm")}
          destructive
          busy={deleteSeasonMutation.isPending}
        />
      ) : null}
      {duplicatingSeason ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDuplicatingSeason(null)}
          onConfirm={handleDuplicateSeason}
          title={t("pricing.seasons.duplicate_confirm.title")}
          description={t("pricing.seasons.duplicate_confirm.description")}
          confirmLabel={t("pricing.seasons.duplicate_confirm.confirm")}
          busy={duplicateSeasonMutation.isPending}
        />
      ) : null}
    </div>
  );
}
