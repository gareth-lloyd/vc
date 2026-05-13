import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { DataTable } from "@/components/data/DataTable";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import type { ColumnDef } from "@tanstack/react-table";
import {
  useDeleteFeature,
  useDeleteFeatureCategory,
  useFeatureCategories,
  useFeatures,
} from "./hooks";
import { FeatureCategoryFormDialog } from "./components/FeatureCategoryFormDialog";
import { FeatureFormDialog } from "./components/FeatureFormDialog";
import type { Feature, FeatureCategory } from "./schemas";

const ALL_CATEGORIES = "__all__";

export function TagsAdminPage() {
  const { t } = useTranslation("admin");
  const canWrite = useHasAdminRole();

  return (
    <AdminPageShell title={t("tags.title")} description={t("tags.description")}>
      <CategoriesSection canWrite={canWrite} />
      <FeaturesSection canWrite={canWrite} />
    </AdminPageShell>
  );
}

function CategoriesSection({ canWrite }: { canWrite: boolean }) {
  const { t } = useTranslation("admin");
  const query = useFeatureCategories({});
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<FeatureCategory | null>(null);
  const [deleting, setDeleting] = useState<FeatureCategory | null>(null);

  const columns: ColumnDef<FeatureCategory>[] = [
    {
      accessorKey: "name",
      header: t("tags.categories.columns.name"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
    },
    {
      accessorKey: "slug",
      header: t("tags.categories.columns.slug"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.slug}</span>,
    },
    {
      accessorKey: "sort_order",
      header: t("tags.categories.columns.sort_order"),
      enableSorting: false,
    },
    {
      accessorKey: "is_active",
      header: t("tags.categories.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge variant="default">{t("users.is_active.yes")}</Badge>
        ) : (
          <Badge variant="secondary">{t("users.is_active.no")}</Badge>
        ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("users.row_actions.menu_label")}
              disabled={!canWrite}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setEditing(row.original)}>
              {t("common.actions.edit")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => setDeleting(row.original)}
              className="text-destructive"
            >
              {t("common.actions.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-base font-semibold">
          {t("tags.categories.section_title")}
        </h2>
        <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!canWrite}>
          {t("tags.categories.new_button")}
        </Button>
      </div>
      {query.isError ? (
        <ErrorState
          description={t("tags.categories.errors.load_failed")}
          onRetry={() => query.refetch()}
          retrying={query.isFetching}
        />
      ) : (
        <DataTable
          columns={columns}
          data={query.data?.results}
          isLoading={query.isLoading}
          pageIndex={0}
          pageCount={1}
          pageSize={100}
          sorting={[]}
          onSortingChange={() => {}}
          onPageChange={() => {}}
          rowKey={(row) => row.id}
          emptyContent={
            <EmptyState
              title={t("tags.categories.empty.title")}
              description={t("tags.categories.empty.description")}
            />
          }
        />
      )}

      {createOpen ? (
        <FeatureCategoryFormDialog mode="create" open={createOpen} onOpenChange={setCreateOpen} />
      ) : null}
      {editing ? (
        <FeatureCategoryFormDialog
          mode="edit"
          category={editing}
          open={editing != null}
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
        />
      ) : null}
      {deleting ? (
        <DeleteCategoryConfirm category={deleting} onClose={() => setDeleting(null)} />
      ) : null}
    </section>
  );
}

function DeleteCategoryConfirm({
  category,
  onClose,
}: {
  category: FeatureCategory;
  onClose: () => void;
}) {
  const { t } = useTranslation("admin");
  const mutation = useDeleteFeatureCategory(category.id);
  const onConfirm = async () => {
    try {
      await mutation.mutateAsync();
      toast.success(t("tags.categories.toasts.deleted"));
      onClose();
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      onConfirm={onConfirm}
      title={t("tags.categories.confirm_delete.title")}
      description={t("tags.categories.confirm_delete.description")}
      confirmLabel={t("tags.categories.confirm_delete.confirm")}
      busy={mutation.isPending}
      destructive
    />
  );
}

function FeaturesSection({ canWrite }: { canWrite: boolean }) {
  const { t } = useTranslation("admin");
  const [categoryFilter, setCategoryFilter] = useState<string>(ALL_CATEGORIES);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Feature | null>(null);
  const [deleting, setDeleting] = useState<Feature | null>(null);

  const categoriesQuery = useFeatureCategories({});
  const categories = categoriesQuery.data?.results ?? [];
  const categoriesById = new Map<number, FeatureCategory>(categories.map((c) => [c.id, c]));

  const featuresQuery = useFeatures({
    category: categoryFilter === ALL_CATEGORIES ? undefined : Number(categoryFilter),
  });

  const columns: ColumnDef<Feature>[] = [
    {
      accessorKey: "name",
      header: t("tags.features.columns.name"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
    },
    {
      accessorKey: "category",
      header: t("tags.features.columns.category"),
      enableSorting: false,
      cell: ({ row }) => {
        const cat = categoriesById.get(row.original.category);
        return cat ? cat.name : `#${row.original.category}`;
      },
    },
    {
      accessorKey: "slug",
      header: t("tags.features.columns.slug"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.slug}</span>,
    },
    {
      accessorKey: "service_type",
      header: t("tags.features.columns.kind"),
      enableSorting: false,
      cell: ({ row }) => {
        const key = `tags.features.service_type.${row.original.service_type}`;
        const label = t(key as "tags.features.service_type.amenity");
        return <Badge variant="outline">{label === key ? row.original.service_type : label}</Badge>;
      },
    },
    {
      accessorKey: "sort_order",
      header: t("tags.features.columns.sort_order"),
      enableSorting: false,
    },
    {
      accessorKey: "is_active",
      header: t("tags.features.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge variant="default">{t("users.is_active.yes")}</Badge>
        ) : (
          <Badge variant="secondary">{t("users.is_active.no")}</Badge>
        ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("users.row_actions.menu_label")}
              disabled={!canWrite}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setEditing(row.original)}>
              {t("common.actions.edit")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => setDeleting(row.original)}
              className="text-destructive"
            >
              {t("common.actions.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-base font-semibold">
          {t("tags.features.section_title")}
        </h2>
        <div className="flex items-center gap-2">
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger
              className="w-[200px]"
              aria-label={t("tags.features.filters.category_label")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_CATEGORIES}>
                {t("tags.features.filters.category_any")}
              </SelectItem>
              {categories.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            onClick={() => setCreateOpen(true)}
            disabled={!canWrite || categories.length === 0}
          >
            {t("tags.features.new_button")}
          </Button>
        </div>
      </div>
      {featuresQuery.isError ? (
        <ErrorState
          description={t("tags.features.errors.load_failed")}
          onRetry={() => featuresQuery.refetch()}
          retrying={featuresQuery.isFetching}
        />
      ) : (
        <DataTable
          columns={columns}
          data={featuresQuery.data?.results}
          isLoading={featuresQuery.isLoading}
          pageIndex={0}
          pageCount={1}
          pageSize={100}
          sorting={[]}
          onSortingChange={() => {}}
          onPageChange={() => {}}
          rowKey={(row) => row.id}
          emptyContent={
            <EmptyState
              title={t("tags.features.empty.title")}
              description={t("tags.features.empty.description")}
            />
          }
        />
      )}

      {createOpen ? (
        <FeatureFormDialog
          mode="create"
          open={createOpen}
          onOpenChange={setCreateOpen}
          categories={categories}
        />
      ) : null}
      {editing ? (
        <FeatureFormDialog
          mode="edit"
          feature={editing}
          open={editing != null}
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
          categories={categories}
        />
      ) : null}
      {deleting ? (
        <DeleteFeatureConfirm feature={deleting} onClose={() => setDeleting(null)} />
      ) : null}
    </section>
  );
}

function DeleteFeatureConfirm({ feature, onClose }: { feature: Feature; onClose: () => void }) {
  const { t } = useTranslation("admin");
  const mutation = useDeleteFeature(feature.id);
  const onConfirm = async () => {
    try {
      await mutation.mutateAsync();
      toast.success(t("tags.features.toasts.deleted"));
      onClose();
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      onConfirm={onConfirm}
      title={t("tags.features.confirm_delete.title")}
      description={t("tags.features.confirm_delete.description")}
      confirmLabel={t("tags.features.confirm_delete.confirm")}
      busy={mutation.isPending}
      destructive
    />
  );
}
