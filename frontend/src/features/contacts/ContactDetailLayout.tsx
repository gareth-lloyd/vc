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
import { useContact, useDeleteContact } from "./hooks";
import { contactDisplayName } from "./display";
import { ContactFormDialog } from "./components/ContactFormDialog";
import { TagChips } from "./components/TagChips";
import type { Contact } from "./schemas";

const CONTACT_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "properties", labelKey: "tabs.properties" },
  { slug: "notes", labelKey: "tabs.notes" },
  { slug: "audit", labelKey: "tabs.audit" },
] as const;
export type ContactTabSlug = (typeof CONTACT_TABS)[number]["slug"];
export const CONTACT_TAB_SLUGS: readonly ContactTabSlug[] = CONTACT_TABS.map((t) => t.slug);

export interface ContactOutletContext {
  contact: Contact;
}

function HeaderActions({ contact }: { contact: Contact }) {
  const { t } = useTranslation("contacts");
  const navigate = useNavigate();
  const canWrite = useHasReservationsRole();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const deleteMutation = useDeleteContact(contact.id);

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync();
      toast.success(t("toasts.deleted"));
      navigate("/contacts");
    } catch (error) {
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
        <ContactFormDialog
          mode="edit"
          contactId={contact.id}
          contact={contact}
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

function RailSummary({ contact }: { contact: Contact }) {
  const name = contactDisplayName(contact);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground font-serif text-lg font-semibold">{name}</h2>
        {contact.agency_detail?.name && (contact.first_name || contact.last_name) ? (
          <p className="text-muted-foreground text-sm">{contact.agency_detail.name}</p>
        ) : null}
      </div>
      {contact.status ? <StatusBadge status={contact.status} /> : null}
      {(contact.tags ?? []).length > 0 ? <TagChips tags={contact.tags ?? []} /> : null}
    </div>
  );
}

export function ContactDetailLayout() {
  const { t } = useTranslation("contacts");
  const { id } = useParams<{ id: string }>();
  const query = useContact(id);

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

  const contact = query.data;
  const name = contactDisplayName(contact);

  return (
    <div>
      <PageHeader
        title={name}
        subtitle={
          contact.agency_detail?.name && (contact.first_name || contact.last_name)
            ? contact.agency_detail.name
            : undefined
        }
        breadcrumbs={[{ label: t("headings.list_title"), to: "/contacts" }, { label: name }]}
        actions={<HeaderActions contact={contact} />}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("headings.sections_aria")}>
          {CONTACT_TABS.map((tab) => (
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

      <TwoColumn rightRail={<RailSummary contact={contact} />}>
        <Outlet context={{ contact } satisfies ContactOutletContext} />
      </TwoColumn>
    </div>
  );
}
