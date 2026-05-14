import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { StagedLine } from "../schemas";

interface Props {
  lines: StagedLine[];
  currency: string;
  onRemove: (propertyId: number) => void;
}

export function QuoteLinesPanel({ lines, currency, onRemove }: Props) {
  const { t } = useTranslation("quotations");

  if (lines.length === 0) {
    return (
      <EmptyState
        title={t("builder.staged.empty.title")}
        description={t("builder.staged.empty.description")}
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("builder.staged.columns.property")}</TableHead>
          <TableHead>{t("builder.staged.columns.dates")}</TableHead>
          <TableHead>{t("builder.staged.columns.guests")}</TableHead>
          <TableHead className="text-right">{t("builder.staged.columns.total")}</TableHead>
          <TableHead className="text-right">{t("builder.staged.columns.actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => (
          <TableRow key={line.property_id}>
            <TableCell className="font-medium">{line.property_name}</TableCell>
            <TableCell>
              {formatDate(line.date_from)} – {formatDate(line.date_to)}
            </TableCell>
            <TableCell>
              {line.adults}A{line.children ? ` · ${line.children}C` : ""}
            </TableCell>
            <TableCell className="text-right">
              {formatMoney(line.total ?? null, currency)}
            </TableCell>
            <TableCell className="text-right">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onRemove(line.property_id)}
              >
                {t("builder.staged.remove")}
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
