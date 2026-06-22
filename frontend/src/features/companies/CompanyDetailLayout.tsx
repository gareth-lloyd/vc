import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useCompany, useDeleteCompany } from "./hooks";
import { companyDisplayName } from "./display";
import { CompanyFormDialog } from "./components/CompanyFormDialog";
import type { Company } from "./schemas";

const COMPANY_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "audit", labelKey: "tabs.audit" },
] as const;
export type CompanyTabSlug = (typeof COMPANY_TABS)[number]["slug"];
export const COMPANY_TAB_SLUGS: readonly CompanyTabSlug[] = COMPANY_TABS.map((t) => t.slug);

export interface CompanyOutletContext {
  company: Company;
}

function HeaderActions({ company }: { company: Company }) {
  const { t } = useTranslation("companies");
  const navigate = useNavigate();
  const canWrite = useHasReservationsRole();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const deleteMutation = useDeleteCompany(company.id);

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync();
      toast.success(t("toasts.deleted"));
      navigate("/companies");
    } catch (error) {
      // A PROTECT FK violation (the org still has agents) returns 409
      // `{code:"protected"}` via the global handler — surface a specific toast.
      if (error instanceof ApiError && error.code === "protected") {
        toast.error(t("toasts.delete_protected"));
        return;
      }
      const message = error instanceof ApiError ? error.detail : t("common:errors.generic");
      toast.error(message);
    }
  };

  const editButton = canWrite ? (
    <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
      {t("common:actions.edit")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button variant="outline" size="sm" disabled>
            {t("common:actions.edit")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  const deleteButton = canWrite ? (
    <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
      {t("common:actions.delete")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button variant="destructive" size="sm" disabled>
            {t("common:actions.delete")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  return (
    <>
      {editButton}
      {deleteButton}
      {editOpen ? (
        <CompanyFormDialog
          mode="edit"
          companyId={company.id}
          company={company}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      ) : null}
      {deleteOpen ? (
        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          onConfirm={handleDelete}
          title={t("confirm.delete_title")}
          description={t("confirm.delete_body")}
          confirmLabel={t("common:actions.delete")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </>
  );
}

function RailSummary({ company }: { company: Company }) {
  const name = companyDisplayName(company);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground font-serif text-lg font-semibold">{name}</h2>
        {company.town ? <p className="text-muted-foreground text-sm">{company.town}</p> : null}
      </div>
      {company.status ? <StatusBadge status={company.status} /> : null}
    </div>
  );
}

export function CompanyDetailLayout() {
  const { t } = useTranslation("companies");
  const { id } = useParams<{ id: string }>();
  const query = useCompany(id);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    const is404 = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={is404 ? t("errors.detail_not_found_title") : t("errors.detail_load_failed_title")}
          description={
            is404 ? t("errors.detail_not_found_body") : t("errors.detail_load_failed_body")
          }
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const company = query.data;
  const name = companyDisplayName(company);

  return (
    <div>
      <PageHeader
        title={name}
        subtitle={company.town ?? undefined}
        breadcrumbs={[{ label: t("headings.list_title"), to: "/companies" }, { label: name }]}
        actions={<HeaderActions company={company} />}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("headings.sections_aria")}>
          {COMPANY_TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tab.slug}
              className={({ isActive }) =>
                cn(
                  "border-b-2 px-3 py-2 text-sm font-medium",
                  isActive
                    ? "border-foreground text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )
              }
            >
              {t(tab.labelKey)}
            </NavLink>
          ))}
        </nav>
      </div>

      <TwoColumn rightRail={<RailSummary company={company} />}>
        <Outlet context={{ company } satisfies CompanyOutletContext} />
      </TwoColumn>
    </div>
  );
}
