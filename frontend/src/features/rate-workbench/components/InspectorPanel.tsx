import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { ServiceFormDialog } from "@/features/properties/components/ServiceFormDialog";
import {
  useDeletePropertyService,
  usePropertyDiscounts,
  usePropertyExtras,
  usePropertyServices,
} from "@/features/properties/hooks";
import type { Discount, Extra, PropertyService } from "@/features/properties/schemas";
import { useDeleteDiscount, useDeleteExtra } from "../hooks";
import { ExtraFormDialog } from "./ExtraFormDialog";
import { DiscountFormDialog } from "./DiscountFormDialog";

interface InspectorPanelProps {
  propertyId: number;
  canWrite: boolean;
  currencyCode: string | null;
  /** The property's currency FK id (from a season), seeding new extras. */
  defaultCurrencyId: number | null;
  /** Currency FK ids across the property's rate plans (extras currency hint). */
  planCurrencyIds?: number[];
}

/**
 * Inline inspectors for a property's inclusions, extras and discounts. Each write
 * invalidates the same list query key the timeline's `toLanes` reads, so editing
 * here refreshes the corresponding lane. Inclusions reuse the existing
 * `ServiceFormDialog`; extras/discounts use the workbench's own form dialogs.
 */
export function InspectorPanel({
  propertyId,
  canWrite,
  currencyCode,
  defaultCurrencyId,
  planCurrencyIds,
}: InspectorPanelProps) {
  const { t } = useTranslation("properties");
  return (
    <section className="border-border space-y-6 border-t pt-6">
      <h2 className="text-foreground text-lg font-semibold">
        {t("rate_workbench.inspector.title")}
      </h2>
      <InclusionsSection propertyId={propertyId} canWrite={canWrite} />
      <ExtrasSection
        propertyId={propertyId}
        canWrite={canWrite}
        currencyCode={currencyCode}
        defaultCurrencyId={defaultCurrencyId}
        planCurrencyIds={planCurrencyIds}
      />
      <DiscountsSection propertyId={propertyId} canWrite={canWrite} currencyCode={currencyCode} />
    </section>
  );
}

function AddButton({
  canWrite,
  label,
  onClick,
}: {
  canWrite: boolean;
  label: string;
  onClick: () => void;
}) {
  const { t } = useTranslation("properties");
  if (canWrite) {
    return (
      <Button size="sm" variant="outline" onClick={onClick}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        {label}
      </Button>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            <Plus className="mr-1 h-3.5 w-3.5" />
            {label}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("rate_workbench.inspector.add_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );
}

function SectionShell({
  title,
  addLabel,
  canWrite,
  onAdd,
  children,
}: {
  title: string;
  addLabel: string;
  canWrite: boolean;
  onAdd: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-foreground text-sm font-semibold">{title}</h3>
        <AddButton canWrite={canWrite} label={addLabel} onClick={onAdd} />
      </div>
      {children}
    </div>
  );
}

function InspectorRow({
  name,
  meta,
  canWrite,
  onEdit,
  onDelete,
}: {
  name: string;
  meta: string | null;
  canWrite: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation("properties");
  return (
    <li className="border-border flex items-center justify-between gap-4 border-b py-2 last:border-b-0">
      <div className="min-w-0">
        <p className="text-foreground truncate text-sm">{name}</p>
        {meta ? <p className="text-muted-foreground truncate text-xs">{meta}</p> : null}
      </div>
      {canWrite ? (
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label={t("rate_workbench.inspector.actions.edit")}
            onClick={onEdit}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive h-7 w-7"
            aria-label={t("rate_workbench.inspector.actions.delete")}
            onClick={onDelete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function dateRange(from: string | null | undefined, to: string | null | undefined): string | null {
  if (!from && !to) return null;
  return `${from ? formatDate(from) : "…"} – ${to ? formatDate(to) : "…"}`;
}

function InclusionsSection({ propertyId, canWrite }: { propertyId: number; canWrite: boolean }) {
  const { t } = useTranslation("properties");
  const services = usePropertyServices(propertyId);
  const deleteService = useDeletePropertyService(propertyId);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<PropertyService | null>(null);
  const [deleting, setDeleting] = useState<PropertyService | null>(null);
  const rows = services.data?.results ?? [];

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteService.mutateAsync({ serviceId: deleting.id });
      toast.success(t("rate_workbench.inspector.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("rate_workbench.inspector.toasts.delete_failed"));
    }
  };

  return (
    <SectionShell
      title={t("rate_workbench.inspector.sections.inclusions")}
      addLabel={t("rate_workbench.inspector.add_inclusion")}
      canWrite={canWrite}
      onAdd={() => setCreating(true)}
    >
      {rows.length === 0 ? (
        <EmptyState title={t("rate_workbench.inspector.empty_inclusions")} />
      ) : (
        <ul>
          {rows.map((s) => (
            <InspectorRow
              key={s.id}
              name={s.name}
              meta={dateRange(s.applies_from, s.applies_to)}
              canWrite={canWrite}
              onEdit={() => setEditing(s)}
              onDelete={() => setDeleting(s)}
            />
          ))}
        </ul>
      )}

      {creating ? (
        <ServiceFormDialog
          propertyId={propertyId}
          open={creating}
          onOpenChange={setCreating}
          mode="create"
        />
      ) : null}
      {editing ? (
        <ServiceFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          service={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("rate_workbench.inspector.delete_confirm.title")}
          description={t("rate_workbench.inspector.delete_confirm.description")}
          confirmLabel={t("rate_workbench.inspector.delete_confirm.confirm")}
          destructive
          busy={deleteService.isPending}
        />
      ) : null}
    </SectionShell>
  );
}

function ExtrasSection({
  propertyId,
  canWrite,
  currencyCode,
  defaultCurrencyId,
  planCurrencyIds,
}: {
  propertyId: number;
  canWrite: boolean;
  currencyCode: string | null;
  defaultCurrencyId: number | null;
  planCurrencyIds?: number[];
}) {
  const { t } = useTranslation("properties");
  const extras = usePropertyExtras(propertyId);
  const deleteExtra = useDeleteExtra(propertyId);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Extra | null>(null);
  const [deleting, setDeleting] = useState<Extra | null>(null);
  const rows = extras.data?.results ?? [];

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteExtra.mutateAsync({ extraId: deleting.id });
      toast.success(t("rate_workbench.inspector.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("rate_workbench.inspector.toasts.delete_failed"));
    }
  };

  const metaFor = (e: Extra): string | null => {
    const parts = [
      e.amount != null ? formatMoney(e.amount, e.currency_code ?? currencyCode) : null,
      e.is_mandatory
        ? t("rate_workbench.inspector.mandatory")
        : t("rate_workbench.inspector.optional"),
      dateRange(e.applies_from, e.applies_to),
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : null;
  };

  return (
    <SectionShell
      title={t("rate_workbench.inspector.sections.extras")}
      addLabel={t("rate_workbench.inspector.add_extra")}
      canWrite={canWrite}
      onAdd={() => setCreating(true)}
    >
      {rows.length === 0 ? (
        <EmptyState title={t("rate_workbench.inspector.empty_extras")} />
      ) : (
        <ul>
          {rows.map((e) => (
            <InspectorRow
              key={e.id}
              name={e.name}
              meta={metaFor(e)}
              canWrite={canWrite}
              onEdit={() => setEditing(e)}
              onDelete={() => setDeleting(e)}
            />
          ))}
        </ul>
      )}

      {creating ? (
        <ExtraFormDialog
          propertyId={propertyId}
          open={creating}
          onOpenChange={setCreating}
          mode="create"
          currencyCode={currencyCode}
          defaultCurrencyId={defaultCurrencyId}
          planCurrencyIds={planCurrencyIds}
        />
      ) : null}
      {editing ? (
        <ExtraFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          entity={editing}
          currencyCode={currencyCode}
          defaultCurrencyId={defaultCurrencyId}
          planCurrencyIds={planCurrencyIds}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("rate_workbench.inspector.delete_confirm.title")}
          description={t("rate_workbench.inspector.delete_confirm.description")}
          confirmLabel={t("rate_workbench.inspector.delete_confirm.confirm")}
          destructive
          busy={deleteExtra.isPending}
        />
      ) : null}
    </SectionShell>
  );
}

function DiscountsSection({
  propertyId,
  canWrite,
  currencyCode,
}: {
  propertyId: number;
  canWrite: boolean;
  currencyCode: string | null;
}) {
  const { t } = useTranslation("properties");
  const discounts = usePropertyDiscounts(propertyId);
  const deleteDiscount = useDeleteDiscount(propertyId);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Discount | null>(null);
  const [deleting, setDeleting] = useState<Discount | null>(null);
  const rows = discounts.data?.results ?? [];

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteDiscount.mutateAsync({ discountId: deleting.id });
      toast.success(t("rate_workbench.inspector.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("rate_workbench.inspector.toasts.delete_failed"));
    }
  };

  const metaFor = (d: Discount): string | null => {
    const kind = d.kind ?? d.rule_kind ?? null;
    const parts = [
      d.code,
      kind,
      d.amount != null ? formatMoney(d.amount, currencyCode) : null,
      dateRange(d.valid_from, d.valid_to),
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : null;
  };

  return (
    <SectionShell
      title={t("rate_workbench.inspector.sections.discounts")}
      addLabel={t("rate_workbench.inspector.add_discount")}
      canWrite={canWrite}
      onAdd={() => setCreating(true)}
    >
      {rows.length === 0 ? (
        <EmptyState title={t("rate_workbench.inspector.empty_discounts")} />
      ) : (
        <ul>
          {rows.map((d) => (
            <InspectorRow
              key={d.id}
              name={d.name}
              meta={metaFor(d)}
              canWrite={canWrite}
              onEdit={() => setEditing(d)}
              onDelete={() => setDeleting(d)}
            />
          ))}
        </ul>
      )}

      {creating ? (
        <DiscountFormDialog
          propertyId={propertyId}
          open={creating}
          onOpenChange={setCreating}
          mode="create"
          currencyCode={currencyCode}
        />
      ) : null}
      {editing ? (
        <DiscountFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          entity={editing}
          currencyCode={currencyCode}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("rate_workbench.inspector.delete_confirm.title")}
          description={t("rate_workbench.inspector.delete_confirm.description")}
          confirmLabel={t("rate_workbench.inspector.delete_confirm.confirm")}
          destructive
          busy={deleteDiscount.isPending}
        />
      ) : null}
    </SectionShell>
  );
}
