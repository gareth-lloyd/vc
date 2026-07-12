import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format/date";
import { formatMoneyWithCode, parseMoney } from "@/lib/format/money";
import { propertyDetailsPath } from "@/lib/routes";
import type { QuotationLine } from "../schemas";
import { PropertyThumbnail } from "./PropertyThumbnail";
import { ChangeoverShiftedNote } from "./ChangeoverShiftedNote";

interface Props {
  line: QuotationLine;
  canWrite: boolean;
  quoteEditable: boolean;
  canBook: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onHold: () => void;
  onReleaseHold: () => void;
  onBook: () => void;
}

export function QuotationLineCard({
  line,
  canWrite,
  quoteEditable,
  canBook,
  onEdit,
  onDelete,
  onHold,
  onReleaseHold,
  onBook,
}: Props) {
  const { t } = useTranslation("quotations");
  const displayName = line.property_name ?? (line.property != null ? `#${line.property}` : "—");
  const discount = parseMoney(line.discount);
  const inclusions = line.inclusions?.trim();

  return (
    <li className="border-border bg-card rounded-md border">
      <div className="flex flex-wrap items-start gap-3 p-3">
        <PropertyThumbnail
          src={line.hero_image_url}
          fallbackText={line.property_name}
          alt={t("detail.lines.thumbnail_alt", { name: displayName })}
        />
        {/* basis-56 + the wrapper's flex-wrap make the action group drop to
            its own row when the viewport is too narrow, instead of clipping. */}
        <div className="min-w-0 flex-1 basis-56">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            {line.property != null ? (
              <Link
                to={propertyDetailsPath(line.property)}
                className="text-foreground truncate text-sm font-semibold hover:underline"
              >
                {displayName}
              </Link>
            ) : (
              <span className="text-foreground truncate text-sm font-semibold">{displayName}</span>
            )}
            <span className="text-muted-foreground font-mono text-xs">#{line.id}</span>
            {line.is_selected ? (
              <Badge variant="secondary">{t("detail.lines.selected_badge")}</Badge>
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs">
            {formatDate(line.date_from ?? null)} – {formatDate(line.date_to ?? null)}
          </p>
          <ChangeoverShiftedNote from={line.changeover_shifted_from} className="mt-0.5" />
          <p className="text-muted-foreground text-xs">
            {line.children
              ? t("detail.lines.party_format_with_children", {
                  adults: line.adults,
                  children: line.children,
                })
              : t("detail.lines.party_format", { adults: line.adults })}{" "}
            ·{" "}
            <span className="text-foreground font-medium tabular-nums">
              {/* Each line is priced in its own currency (GAP-014). */}
              {formatMoneyWithCode(line.total ?? null, line.currency ?? null)}
            </span>
            {Number.isFinite(discount) && discount !== 0 ? (
              <>
                {" "}
                · {t("detail.lines.discount_label")}{" "}
                <span className="tabular-nums">
                  {formatMoneyWithCode(line.discount ?? null, line.currency ?? null)}
                </span>
              </>
            ) : null}
          </p>
          {inclusions ? (
            <p className="text-muted-foreground truncate text-xs">{inclusions}</p>
          ) : null}
          {line.hold ? (
            <p className="text-hold text-xs font-medium">
              {t("detail.lines.hold_until", { date: formatDate(line.hold.expires_at ?? null) })}
            </p>
          ) : null}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {line.hold ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onReleaseHold}
              disabled={!canWrite}
            >
              {t("detail.lines.actions.release_hold")}
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onHold}
              disabled={!canWrite || !quoteEditable}
            >
              {t("detail.lines.actions.hold")}
            </Button>
          )}
          <Button type="button" size="sm" variant="ghost" onClick={onBook} disabled={!canBook}>
            {t("detail.lines.actions.book")}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onEdit} disabled={!canWrite}>
            {t("detail.lines.actions.edit")}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onDelete} disabled={!canWrite}>
            {t("detail.lines.actions.remove")}
          </Button>
        </div>
      </div>
    </li>
  );
}
