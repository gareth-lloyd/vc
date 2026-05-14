import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useChangeOverRules, useDeleteChangeOverRule } from "../hooks";
import type { ChangeOverRule } from "../schemas";
import { ChangeoverRuleFormDialog } from "./ChangeoverRuleFormDialog";

interface ChangeoverRulesSectionProps {
  propertyId: number;
}

export function ChangeoverRulesSection({ propertyId }: ChangeoverRulesSectionProps) {
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const rules = useChangeOverRules(propertyId);
  const deleteMutation = useDeleteChangeOverRule(propertyId);

  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ChangeOverRule | null>(null);
  const [deleting, setDeleting] = useState<ChangeOverRule | null>(null);

  const sorted = useMemo(() => {
    const rows = rules.data?.results ?? [];
    return [...rows].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
  }, [rules.data?.results]);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ ruleId: deleting.id });
      toast.success(t("changeover.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("changeover.toasts.delete_failed"));
    }
  };

  if (rules.isLoading) return <Skeleton className="h-24 w-full" />;

  if (rules.isError) {
    return (
      <ErrorState
        description={t("changeover.errors.load_failed")}
        onRetry={() => rules.refetch()}
      />
    );
  }

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("changeover.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("changeover.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("changeover.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-foreground text-sm font-semibold">{t("changeover.title")}</h3>
          <p className="text-muted-foreground text-xs">{t("changeover.description")}</p>
        </div>
        {addButton}
      </div>

      {sorted.length === 0 ? (
        <EmptyState title={t("changeover.empty.title")} />
      ) : (
        <ul className="space-y-2">
          {sorted.map((rule) => (
            <li
              key={rule.id}
              className="border-border bg-card flex items-center justify-between gap-3 rounded-md border p-3 text-sm"
            >
              <div className="space-y-1">
                <p className="text-foreground font-medium">
                  {t(`changeover_days.${rule.weekday}`)}
                </p>
                <p className="text-muted-foreground text-xs">
                  {rule.effective_from} → {rule.effective_to}
                </p>
                {rule.notes ? <p className="text-muted-foreground text-xs">{rule.notes}</p> : null}
              </div>
              {canWrite ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2"
                      aria-label={t("changeover.row.menu_label")}
                    >
                      ···
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(rule)}>
                      {t("changeover.row.edit")}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeleting(rule)}
                    >
                      {t("changeover.row.delete")}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {addOpen ? (
        <ChangeoverRuleFormDialog
          propertyId={propertyId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <ChangeoverRuleFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          rule={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("changeover.delete_confirm.title")}
          description={t("changeover.delete_confirm.description")}
          confirmLabel={t("changeover.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
