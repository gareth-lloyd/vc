import { useState } from "react";
import { ActivityList } from "@/components/data/ActivityList";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Section } from "@/components/data/Section";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { SeasonFormDialog } from "../components/SeasonFormDialog";
import { ActiveBadge, SeasonDetailPanel } from "../components/SeasonDetailPanel";
import {
  useDeleteSeason,
  useDuplicateSeason,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertySeasons,
} from "../hooks";
import type { Discount, Extra, PropertyDetail, RatePlan } from "../schemas";

interface PricingContext {
  property: PropertyDetail;
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
    <ActivityList as="ul">
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
                {plan.currency_code ? ` · ${plan.currency_code}` : ""}
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
    </ActivityList>
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
            <td className="py-2 pr-2">{formatMoney(extra.amount, extra.currency_code ?? null)}</td>
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
          <SeasonDetailPanel
            propertyId={property.id}
            seasonId={selectedSeasonId}
            onBack={() => setSelectedSeasonId(null)}
            canWrite={canWrite}
          />
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
