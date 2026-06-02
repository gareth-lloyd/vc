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
import { PropertyThumbnail } from "./PropertyThumbnail";
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
          <TableHead className="text-right">{t("builder.staged.columns.discount")}</TableHead>
          <TableHead>{t("builder.staged.columns.inclusions")}</TableHead>
          <TableHead className="text-right">{t("builder.staged.columns.total")}</TableHead>
          <TableHead className="text-right">{t("builder.staged.columns.actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => (
          <TableRow key={line.property_id}>
            <TableCell className="font-medium">
              <div className="flex items-center gap-2">
                <PropertyThumbnail
                  src={line.hero_image_url}
                  fallbackText={line.property_name}
                  alt={t("builder.staged.thumbnail_alt", { name: line.property_name })}
                />
                <span>{line.property_name}</span>
              </div>
            </TableCell>
            <TableCell>
              {formatDate(line.date_from)} – {formatDate(line.date_to)}
            </TableCell>
            <TableCell>
              {line.adults}A{line.children ? ` · ${line.children}C` : ""}
            </TableCell>
            <TableCell className="text-muted-foreground text-right">—</TableCell>
            <TableCell className="text-muted-foreground">—</TableCell>
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
