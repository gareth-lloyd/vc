import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { useQuotation, useQuotationLines } from "./hooks";
import type { QuotationDetail, QuotationLine } from "./schemas";

function LinesSection({ quotationId }: { quotationId: number }) {
  const { t } = useTranslation("quotations");
  const lines = useQuotationLines(quotationId);

  if (lines.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }
  if (lines.isError) {
    return (
      <ErrorState
        description={t("detail.lines.errors.load_failed")}
        onRetry={() => lines.refetch()}
        retrying={lines.isFetching}
      />
    );
  }
  const results = lines.data?.results ?? [];
  if (results.length === 0) {
    return <EmptyState title={t("detail.lines.empty")} />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("detail.lines.columns.id")}</TableHead>
          <TableHead>{t("detail.lines.columns.property")}</TableHead>
          <TableHead>{t("detail.lines.columns.dates")}</TableHead>
          <TableHead>{t("detail.lines.columns.guests")}</TableHead>
          <TableHead className="text-right">{t("detail.lines.columns.total")}</TableHead>
          <TableHead>{t("detail.lines.columns.selected")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {results.map((line: QuotationLine) => (
          <TableRow key={line.id}>
            <TableCell className="font-mono text-xs">#{line.id}</TableCell>
            <TableCell>{line.property != null ? `#${line.property}` : "—"}</TableCell>
            <TableCell>
              {formatDate(line.date_from ?? null)} – {formatDate(line.date_to ?? null)}
            </TableCell>
            <TableCell>
              {line.adults}A{line.children ? ` · ${line.children}C` : ""}
            </TableCell>
            <TableCell className="text-right">
              {line.total != null ? String(line.total) : "—"}
            </TableCell>
            <TableCell>
              {line.is_selected ? t("detail.lines.selected_yes") : t("detail.lines.selected_no")}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function DisabledActionButton({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block">
          <Button variant="outline" size="sm" className="w-full justify-start" disabled>
            {label}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}

function RailSummary({ quotation }: { quotation: QuotationDetail }) {
  const { t } = useTranslation("quotations");
  const comingSoon = t("detail.actions.coming_soon");
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{quotation.reference}</h2>
        <p className="text-muted-foreground text-sm">{t("detail.summary.title")}</p>
      </div>
      <StatusBadge status={quotation.status} />
      <FactList>
        <FactRow
          label={t("detail.summary.enquiry")}
          value={quotation.enquiry != null ? `#${quotation.enquiry}` : "—"}
        />
        <FactRow
          label={t("detail.summary.guest")}
          value={quotation.guest != null ? `#${quotation.guest}` : "—"}
        />
        <FactRow
          label={t("detail.summary.agent")}
          value={quotation.agent != null ? `#${quotation.agent}` : "—"}
        />
        <FactRow label={t("detail.summary.currency")} value={quotation.currency ?? "—"} />
        <FactRow
          label={t("detail.summary.expires_at")}
          value={formatDate(quotation.expires_at ?? null)}
        />
        <FactRow
          label={t("detail.summary.created_at")}
          value={formatDate(quotation.created_at ?? null)}
        />
      </FactList>
      <div className="space-y-2">
        <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("detail.actions.section_label")}
        </p>
        <DisabledActionButton label={t("detail.actions.send")} tooltip={comingSoon} />
        <DisabledActionButton label={t("detail.actions.duplicate")} tooltip={comingSoon} />
        <DisabledActionButton label={t("detail.actions.convert")} tooltip={comingSoon} />
        <DisabledActionButton label={t("detail.actions.withdraw")} tooltip={comingSoon} />
      </div>
    </div>
  );
}

export function QuotationDetailLayout() {
  const { t } = useTranslation("quotations");
  const { id } = useParams<{ id: string }>();
  const query = useQuotation(id);

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
          title={is404 ? t("detail.errors.not_found") : t("detail.errors.load_failed")}
          description={
            is404
              ? t("detail.errors.not_found_description")
              : t("detail.errors.load_failed_description")
          }
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const quotation = query.data;

  return (
    <div>
      <PageHeader
        title={quotation.reference}
        breadcrumbs={[
          { label: t("detail.breadcrumb_root") },
          { label: t("detail.breadcrumb_list"), to: "/quotations" },
          { label: quotation.reference },
        ]}
      />

      <TwoColumn rightRail={<RailSummary quotation={quotation} />}>
        <section className="space-y-3">
          <h3 className="text-foreground text-base font-semibold">{t("detail.lines.title")}</h3>
          <LinesSection quotationId={quotation.id} />
        </section>
      </TwoColumn>
    </div>
  );
}
