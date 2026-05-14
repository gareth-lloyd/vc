import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDateTime } from "@/lib/format/date";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { useSystemSettings, useUpdateSystemSettings } from "./hooks";

type Row = { key: string; value: string };

function settingsToRows(settings: Record<string, unknown>): Row[] {
  return Object.entries(settings)
    .map(([key, value]) => ({
      key,
      value: typeof value === "string" ? value : JSON.stringify(value),
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

function rowsToSettings(rows: Row[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    let parsed: unknown = row.value;
    if (row.value === "true") parsed = true;
    else if (row.value === "false") parsed = false;
    else if (row.value !== "" && !Number.isNaN(Number(row.value))) {
      try {
        parsed = JSON.parse(row.value);
      } catch {
        parsed = row.value;
      }
    } else {
      try {
        parsed = JSON.parse(row.value);
      } catch {
        parsed = row.value;
      }
    }
    out[row.key] = parsed;
  }
  return out;
}

export function SystemAdminPage() {
  const { t } = useTranslation("admin");
  const canWrite = useHasAdminRole();
  const query = useSystemSettings();
  const updateMutation = useUpdateSystemSettings();

  const initialRows = useMemo(
    () => settingsToRows(query.data?.settings ?? {}),
    [query.data?.settings],
  );
  const [rows, setRows] = useState<Row[]>(initialRows);
  const [addOpen, setAddOpen] = useState(false);

  useEffect(() => {
    setRows(initialRows);
  }, [initialRows]);

  const dirty = useMemo(() => {
    if (rows.length !== initialRows.length) return true;
    const a = [...rows].sort((r1, r2) => r1.key.localeCompare(r2.key));
    const b = [...initialRows].sort((r1, r2) => r1.key.localeCompare(r2.key));
    return a.some((r, i) => r.key !== b[i].key || r.value !== b[i].value);
  }, [rows, initialRows]);

  const updateRow = (index: number, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, value } : r)));
  };
  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
  };
  const addRow = (key: string, value: string) => {
    setRows((prev) => [...prev, { key, value }]);
  };

  const handleSave = async () => {
    try {
      const settings = rowsToSettings(rows);
      await updateMutation.mutateAsync({ settings });
      toast.success(t("system.toasts.updated"));
    } catch {
      toast.error(t("system.errors.save_failed"));
    }
  };

  const handleDiscard = () => setRows(initialRows);

  const actions = (
    <div className="flex items-center gap-2">
      {dirty ? (
        <Button
          variant="outline"
          size="sm"
          onClick={handleDiscard}
          disabled={updateMutation.isPending}
        >
          {t("system.actions.discard")}
        </Button>
      ) : null}
      <Button size="sm" variant="outline" onClick={() => setAddOpen(true)} disabled={!canWrite}>
        {t("system.actions.add_key")}
      </Button>
      <Button
        size="sm"
        onClick={handleSave}
        disabled={!canWrite || !dirty || updateMutation.isPending}
      >
        {updateMutation.isPending ? t("common:actions.saving") : t("system.actions.save_all")}
      </Button>
    </div>
  );

  const existingKeys = useMemo(() => new Set(rows.map((r) => r.key)), [rows]);

  return (
    <AdminPageShell
      title={t("system.title")}
      description={t("system.description")}
      actions={actions}
    >
      {query.data?.updated_at ? (
        <p className="text-muted-foreground text-sm">
          {t("system.updated_at_label")}: {formatDateTime(query.data.updated_at)}
        </p>
      ) : null}

      {query.isError ? (
        <ErrorState
          description={t("system.errors.load_failed")}
          onRetry={() => query.refetch()}
          retrying={query.isFetching}
        />
      ) : query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title={t("system.empty.title")} description={t("system.empty.description")} />
      ) : (
        <div className="space-y-2">
          {rows.map((row, index) => (
            <div
              key={`${row.key}-${index}`}
              className="grid grid-cols-[200px_1fr_auto] items-center gap-3"
            >
              <Label htmlFor={`sys-${row.key}`} className="font-mono text-sm">
                {row.key}
              </Label>
              <Input
                id={`sys-${row.key}`}
                value={row.value}
                onChange={(e) => updateRow(index, e.target.value)}
                disabled={!canWrite}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeRow(index)}
                disabled={!canWrite}
              >
                {t("system.actions.delete_row")}
              </Button>
            </div>
          ))}
        </div>
      )}

      {addOpen ? (
        <AddKeyDialog
          open={addOpen}
          existingKeys={existingKeys}
          onOpenChange={setAddOpen}
          onAdd={addRow}
        />
      ) : null}
    </AdminPageShell>
  );
}

function AddKeyDialog({
  open,
  onOpenChange,
  onAdd,
  existingKeys,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (key: string, value: string) => void;
  existingKeys: Set<string>;
}) {
  const { t } = useTranslation("admin");
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setKey("");
      setValue("");
      setError(null);
    }
  }, [open]);

  const handleSubmit = () => {
    const trimmed = key.trim();
    if (!trimmed) {
      setError(t("system.add_key_dialog.errors.key_required"));
      return;
    }
    if (existingKeys.has(trimmed)) {
      setError(t("system.add_key_dialog.errors.key_duplicate"));
      return;
    }
    onAdd(trimmed, value);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("system.add_key_dialog.title")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="add-key">{t("system.add_key_dialog.key_label")}</Label>
            <Input
              id="add-key"
              placeholder={t("system.add_key_dialog.key_placeholder")}
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="add-value">{t("system.add_key_dialog.value_label")}</Label>
            <Input
              id="add-value"
              placeholder={t("system.add_key_dialog.value_placeholder")}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          {error ? (
            <p className="text-destructive text-sm" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common:actions.cancel")}
          </Button>
          <Button onClick={handleSubmit}>{t("system.add_key_dialog.submit")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
