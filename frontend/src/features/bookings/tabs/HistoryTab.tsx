import { useOutletContext } from "react-router-dom";
import { AuditHistory } from "@/features/audit/AuditHistory";
import type { BookingOutletContext } from "../BookingDetailLayout";

export function HistoryTab() {
  const { booking } = useOutletContext<BookingOutletContext>();
  return (
    <div className="p-6">
      <AuditHistory entityType="reservations.booking" entityId={booking.id} />
    </div>
  );
}
