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
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import type { ContactId } from "@/lib/query/keys";
import { useContactRelationships, useDeleteContactRelationship } from "../hooks";
import { relationshipLabelKey } from "../personRelationships";
import type { LinkedContact, RelationshipPerson } from "../schemas";
import { LinkRelationshipDialog } from "./LinkRelationshipDialog";

interface LinkedContactsAccordionProps {
  contactId: ContactId;
}

function personName(person: RelationshipPerson, fallback: (id: number) => string): string {
  if (person.display_name) return person.display_name;
  const full = [person.first_name, person.last_name].filter(Boolean).join(" ").trim();
  return full || fallback(person.id);
}

export function LinkedContactsAccordion({ contactId }: LinkedContactsAccordionProps) {
  const { t } = useTranslation("contacts");
  const canWrite = useHasReservationsRole();
  const query = useContactRelationships(contactId);
  const deleteMutation = useDeleteContactRelationship(contactId);

  const [linkOpen, setLinkOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const rows = query.data?.results ?? [];
  // `count` is the DRF total; `rows` is one page (size 50). We render no
  // pagination control because a person's standing links (spouse/children/PA/…)
  // never approach a page — if that assumption ever breaks, add paging here.
  const count = query.data?.count ?? 0;

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deleteMutation.mutateAsync({ relId: deletingId });
      toast.success(t("toasts.link_removed"));
      setDeletingId(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : t("toasts.link_remove_failed");
      toast.error(message);
    }
  };

  const linkButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setLinkOpen(true)}>
      {t("actions.link_contact")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            {t("actions.link_contact")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  const renderRow = (rel: LinkedContact) => (
    <li key={rel.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-foreground truncate font-medium">
            {personName(rel.other_person, (id) => t("fallback.name_with_id", { id }))}
          </span>
          <Badge variant="outline">{t(relationshipLabelKey(rel.kind, rel.direction))}</Badge>
        </div>
        {rel.note ? <span className="text-muted-foreground text-xs">{rel.note}</span> : null}
      </div>
      {canWrite ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              {t("actions.actions_menu_aria")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem className="text-destructive" onClick={() => setDeletingId(rel.id)}>
              {t("common:actions.remove")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </li>
  );

  return (
    <Collapsible
      className="rounded-md border"
      headerClassName="px-3 py-2 text-sm font-medium"
      toggleAriaLabel={t("headings.linked_contacts", { count })}
      title={<span>{t("headings.linked_contacts", { count })}</span>}
    >
      <div className="border-border border-t">
        <div className="flex items-center justify-end px-3 py-2">{linkButton}</div>
        {query.isLoading ? (
          <div className="space-y-2 p-3">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : query.isError ? (
          <p className="text-destructive px-3 py-2 text-sm">
            {t("errors.relationships_load_failed")}
          </p>
        ) : rows.length === 0 ? (
          <EmptyState title={t("empty.linked_contacts")} />
        ) : (
          <ul className="divide-border divide-y">{rows.map(renderRow)}</ul>
        )}
      </div>

      {linkOpen ? (
        <LinkRelationshipDialog contactId={contactId} open={linkOpen} onOpenChange={setLinkOpen} />
      ) : null}
      {deletingId != null ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingId(null)}
          onConfirm={handleDelete}
          title={t("confirm.remove_link_title")}
          description={t("confirm.remove_link_body")}
          confirmLabel={t("common:actions.remove")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </Collapsible>
  );
}
