import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionButton } from "@/components/feedback/ActionButton";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useEnquiry, useReopenEnquiry } from "./hooks";
import { AssignDialog } from "./components/AssignDialog";
import { CloseDialog } from "./components/CloseDialog";
import { enquirySourceLabel, enquiryStatusLabel, type EnquiryDetail } from "./schemas";

export const ENQUIRY_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "activity", labelKey: "tabs.activity" },
  { slug: "notes", labelKey: "tabs.notes" },
] as const;

export interface EnquiryOutletContext {
  enquiry: EnquiryDetail;
}

type DialogKind = "assign" | "close" | "reopen" | null;

function guestName(enq: EnquiryDetail): string {
  const name = `${enq.first_name ?? ""} ${enq.last_name ?? ""}`.trim();
  return name || enq.email || enq.reference;
}

interface EnquiryActionsProps {
  enquiry: EnquiryDetail;
  onOpen: (dialog: DialogKind) => void;
}

function EnquiryActions({ enquiry, onOpen }: EnquiryActionsProps) {
  const { t } = useTranslation("enquiries");
  const navigate = useNavigate();
  const hasRole = useHasReservationsRole();

  const isClosed = enquiry.status === "lost";
  const isFinal = enquiry.status === "converted" || enquiry.status === "lost";
  const roleRequired = t("common:errors.reservations_role_required");

  const handleConvertClick = () => {
    navigate(`/quotations/new?enquiry=${enquiry.id}`);
  };

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        {t("detail.rail.actions_heading")}
      </p>
      <ActionButton
        label={t("detail.actions.assign")}
        onClick={() => onOpen("assign")}
        disableReason={hasRole ? null : roleRequired}
      />
      <ActionButton
        label={t("detail.actions.convert")}
        onClick={handleConvertClick}
        disableReason={
          !hasRole ? roleRequired : isFinal ? t("detail.actions.convert_disabled_state") : null
        }
      />
      <ActionButton
        label={t("detail.actions.close")}
        onClick={() => onOpen("close")}
        disableReason={
          !hasRole ? roleRequired : isFinal ? t("detail.actions.close_disabled_state") : null
        }
      />
      <ActionButton
        label={t("detail.actions.reopen")}
        onClick={() => onOpen("reopen")}
        disableReason={
          !hasRole ? roleRequired : !isClosed ? t("detail.actions.reopen_disabled_state") : null
        }
      />
    </div>
  );
}

interface RailProps {
  enquiry: EnquiryDetail;
  onOpenDialog: (dialog: DialogKind) => void;
}

function RailSummary({ enquiry, onOpenDialog }: RailProps) {
  const { t } = useTranslation("enquiries");
  const partyText =
    enquiry.children > 0
      ? t("detail.rail.party_format_with_children", {
          adults: enquiry.adults,
          children: enquiry.children,
        })
      : t("detail.rail.party_format", { adults: enquiry.adults });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground font-serif text-lg font-semibold">{enquiry.reference}</h2>
        <p className="text-muted-foreground text-sm">{guestName(enquiry)}</p>
      </div>
      <StatusBadge status={enquiryStatusLabel(enquiry.status)} />
      <FactList>
        <FactRow
          label={t("detail.rail.dates")}
          value={
            enquiry.date_from || enquiry.date_to
              ? `${formatDate(enquiry.date_from ?? null)} – ${formatDate(enquiry.date_to ?? null)}`
              : t("detail.rail.flexible")
          }
        />
        <FactRow label={t("detail.rail.party")} value={partyText} />
        <FactRow label={t("detail.rail.source")} value={enquirySourceLabel(enquiry.site_source)} />
        <FactRow
          label={t("detail.rail.property")}
          value={
            enquiry.property != null
              ? t("detail.rail.property_with_id", { id: enquiry.property })
              : "—"
          }
        />
        <FactRow
          label={t("detail.rail.assigned")}
          value={
            enquiry.assigned_to != null
              ? t("detail.rail.user_with_id", { id: enquiry.assigned_to })
              : t("detail.rail.unassigned")
          }
        />
      </FactList>
      <EnquiryActions enquiry={enquiry} onOpen={onOpenDialog} />
    </div>
  );
}

export function EnquiryDetailLayout() {
  const { t } = useTranslation("enquiries");
  const { id } = useParams<{ id: string }>();
  const query = useEnquiry(id);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const reopenMutation = useReopenEnquiry(id ?? 0);

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
          title={is404 ? t("detail.not_found_title") : t("detail.load_failed_title")}
          description={is404 ? t("detail.not_found_body") : t("detail.load_failed_body")}
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const enquiry = query.data;

  const handleReopen = async () => {
    try {
      await reopenMutation.mutateAsync("");
      toast.success(t("detail.reopen_confirm.success_message"));
      setDialog(null);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.detail : t("detail.reopen_confirm.error_message");
      toast.error(message);
    }
  };

  return (
    <div>
      <PageHeader
        title={enquiry.reference}
        subtitle={guestName(enquiry)}
        breadcrumbs={[
          { label: t("detail.breadcrumb_list"), to: "/enquiries" },
          { label: enquiry.reference },
        ]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("detail.sections_aria")}>
          {ENQUIRY_TABS.map((tab) => (
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

      <TwoColumn rightRail={<RailSummary enquiry={enquiry} onOpenDialog={setDialog} />}>
        <Outlet context={{ enquiry } satisfies EnquiryOutletContext} />
      </TwoColumn>

      {dialog === "assign" && (
        <AssignDialog
          enquiryId={enquiry.id}
          currentUserId={enquiry.assigned_to ?? null}
          open={true}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        />
      )}
      {dialog === "close" && (
        <CloseDialog
          enquiryId={enquiry.id}
          open={true}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        />
      )}
      <ConfirmDialog
        open={dialog === "reopen"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        onConfirm={handleReopen}
        title={t("detail.reopen_confirm.title")}
        description={t("detail.reopen_confirm.description")}
        confirmLabel={t("detail.reopen_confirm.confirm_label")}
        busy={reopenMutation.isPending}
      />
    </div>
  );
}
