import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { formatDate } from "@/lib/format/date";
import { bandDates, type TimelineBand } from "../bands";

interface BandPopoverProps {
  band: TimelineBand;
  /** Slug-safe path to the villa's single-villa availability calendar. */
  villaCalendarPath: string;
}

export function BandPopover({ band, villaCalendarPath }: BandPopoverProps) {
  const { t } = useTranslation("availability");
  const { date_from, date_to } = bandDates(band);
  const dates = `${formatDate(date_from)} – ${formatDate(date_to)}`;

  if (band.kind === "booking") {
    const { booking } = band;
    return (
      <div className="space-y-2 text-sm">
        <p className="font-medium">{booking.guest_name || t("band.no_guest")}</p>
        <dl className="text-muted-foreground space-y-1">
          <div className="flex justify-between gap-4">
            <dt>{t("popover.status")}</dt>
            <dd>{t(`bookings:labels.status.${booking.status}`)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>{t("popover.dates")}</dt>
            <dd>{dates}</dd>
          </div>
        </dl>
        <Link to={`/bookings/${booking.id}`} className="text-primary block font-medium underline">
          {t("popover.open_booking")} — {booking.reference}
        </Link>
      </div>
    );
  }

  const { hold } = band;
  return (
    <div className="space-y-2 text-sm">
      <p className="font-medium">{t(`reason_labels.${hold.reason}`, hold.reason)}</p>
      <dl className="text-muted-foreground space-y-1">
        <div className="flex justify-between gap-4">
          <dt>{t("popover.dates")}</dt>
          <dd>{dates}</dd>
        </div>
        {hold.notes ? (
          <div className="flex justify-between gap-4">
            <dt>{t("popover.notes")}</dt>
            <dd className="text-right">{hold.notes}</dd>
          </div>
        ) : null}
      </dl>
      <Link to={villaCalendarPath} className="text-primary block font-medium underline">
        {t("popover.open_calendar")}
      </Link>
    </div>
  );
}
