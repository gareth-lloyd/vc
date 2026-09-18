// "Imported bookings" (GAP-117 UI name; the backend model is `PastStay`):
// historic stays loaded once by the legacy cutover importers — never a Booking
// made in this app. Shared here because both the client profile
// (features/contacts) and the /bookings tab (features/bookings) render them,
// and features may not import each other. features/contacts/schemas.ts
// re-exports the schema under its original `contactPastStay*` names.
import { z } from "zod";
import { formatDateRangeEndpoints } from "@/lib/format/date";
import { formatMoney, parseMoney } from "@/lib/format/money";

// Mirrors ContactPastStaySerializer. `property` (pk) + `property_name` are set
// when the importer matched the villa name, else null and the row falls back
// to the sheet's `villa_name` text. GAP-113: `date_from`/`date_to` (both or
// neither) and `amount` (decimal string) from the legacy archive;
// `currency_code` null = legacy recorded no currency.
export const importedBookingSchema = z.object({
  id: z.number(),
  booking_number: z.string(),
  villa_name: z.string(),
  property: z.number().nullable(),
  property_name: z.string().nullable(),
  destination: z.string(),
  year: z.number().nullable(),
  notes: z.string(),
  date_from: z.string().nullable(),
  date_to: z.string().nullable(),
  amount: z.string().nullable(),
  currency_code: z.string().nullable(),
});
export type ImportedBooking = z.infer<typeof importedBookingSchema>;

// GAP-113: legacy amounts are shown exactly as staff recorded them. With no
// recorded currency the bare number is shown — a currency is never guessed.
export function recordedAmount(row: ImportedBooking): string | null {
  if (row.amount == null) return null;
  if (row.currency_code) return formatMoney(row.amount, row.currency_code);
  return parseMoney(row.amount).toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Exact dates when the archive supplied them, else the sheet year; null when
// neither is known (the caller renders its own "year unknown" label).
export function importedBookingWhen(row: ImportedBooking): string | null {
  if (row.date_from && row.date_to) return formatDateRangeEndpoints(row.date_from, row.date_to);
  return row.year != null ? String(row.year) : null;
}
