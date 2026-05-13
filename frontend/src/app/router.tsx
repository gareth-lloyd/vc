import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "./guards";
import { BootGate } from "./boot";
import { LoginPage } from "@/features/auth/LoginPage";
import { TfaChallengePage } from "@/features/auth/TfaChallengePage";
import { DashboardPlaceholderPage } from "@/features/dashboard/DashboardPlaceholderPage";
import { PropertiesListPage } from "@/features/properties/PropertiesListPage";
import { PROPERTY_TABS, PropertyDetailLayout } from "@/features/properties/PropertyDetailLayout";
import { DetailsTab } from "@/features/properties/tabs/DetailsTab";
import { PricingTab } from "@/features/properties/tabs/PricingTab";
import { PeopleTab } from "@/features/properties/tabs/PeopleTab";
import { AvailabilityTab } from "@/features/properties/tabs/AvailabilityTab";
import { MediaTab as PropertyMediaTab } from "@/features/properties/tabs/MediaTab";
import { SettingsTab as PropertySettingsTab } from "@/features/properties/tabs/SettingsTab";
import { BookingsListPage } from "@/features/bookings/BookingsListPage";
import { BOOKING_TABS, BookingDetailLayout } from "@/features/bookings/BookingDetailLayout";
import { OverviewTab as BookingOverviewTab } from "@/features/bookings/tabs/OverviewTab";
import { TimelineTab as BookingTimelineTab } from "@/features/bookings/tabs/TimelineTab";
import { NotesTab as BookingNotesTab } from "@/features/bookings/tabs/NotesTab";
import { PaymentsTab as BookingPaymentsTab } from "@/features/bookings/tabs/PaymentsTab";
import { ConciergeTab as BookingConciergeTab } from "@/features/bookings/tabs/ConciergeTab";
import { FinanceTab as BookingFinanceTab } from "@/features/bookings/tabs/FinanceTab";
import { ContactsListPage } from "@/features/contacts/ContactsListPage";
import { ContactDetailLayout } from "@/features/contacts/ContactDetailLayout";
import { DetailsTab as ContactDetailsTab } from "@/features/contacts/tabs/DetailsTab";
import { PropertiesTab as ContactPropertiesTab } from "@/features/contacts/tabs/PropertiesTab";
import { AuditTab as ContactAuditTab } from "@/features/contacts/tabs/AuditTab";
import { EnquiriesListPage } from "@/features/enquiries/EnquiriesListPage";
import { EnquiryDetailLayout } from "@/features/enquiries/EnquiryDetailLayout";
import { DetailsTab as EnquiryDetailsTab } from "@/features/enquiries/tabs/DetailsTab";
import { ActivityTab as EnquiryActivityTab } from "@/features/enquiries/tabs/ActivityTab";
import { NotesTab as EnquiryNotesTab } from "@/features/enquiries/tabs/NotesTab";
import { QuotationsListPage } from "@/features/quotations/QuotationsListPage";
import { QuotationDetailLayout } from "@/features/quotations/QuotationDetailLayout";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";
import { NotFoundPage } from "./NotFoundPage";

const REAL_PROPERTY_TABS = new Set<string>([
  "details",
  "pricing",
  "people",
  "availability",
  "media",
  "settings",
]);
const propertyPlaceholderRoutes = PROPERTY_TABS.filter((t) => !REAL_PROPERTY_TABS.has(t.slug)).map(
  (t) => ({
    path: t.slug,
    element: <ComingSoonTab tabName={t.label} />,
  }),
);

const REAL_BOOKING_TABS = new Set<string>([
  "overview",
  "timeline",
  "notes",
  "payments",
  "concierge",
  "finance",
]);
const bookingPlaceholderRoutes = BOOKING_TABS.filter((t) => !REAL_BOOKING_TABS.has(t.slug)).map(
  (t) => ({
    path: t.slug,
    element: <ComingSoonTab tabName={t.label} />,
  }),
);

export const router = createBrowserRouter([
  {
    element: <BootGate />,
    children: [
      { path: "/", element: <Navigate to="/dashboard" replace /> },
      { path: "/login", element: <LoginPage /> },
      { path: "/login/2fa", element: <TfaChallengePage /> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppShell />,
            children: [
              { path: "/dashboard", element: <DashboardPlaceholderPage /> },
              { path: "/properties", element: <PropertiesListPage /> },
              {
                path: "/properties/:id",
                element: <PropertyDetailLayout />,
                children: [
                  { index: true, element: <Navigate to="details" replace /> },
                  { path: "details", element: <DetailsTab /> },
                  { path: "pricing", element: <PricingTab /> },
                  { path: "people", element: <PeopleTab /> },
                  { path: "availability", element: <AvailabilityTab /> },
                  { path: "media", element: <PropertyMediaTab /> },
                  { path: "settings", element: <PropertySettingsTab /> },
                  ...propertyPlaceholderRoutes,
                ],
              },
              { path: "/contacts", element: <ContactsListPage /> },
              {
                path: "/contacts/:id",
                element: <ContactDetailLayout />,
                children: [
                  { index: true, element: <Navigate to="details" replace /> },
                  { path: "details", element: <ContactDetailsTab /> },
                  { path: "properties", element: <ContactPropertiesTab /> },
                  { path: "notes", element: <ComingSoonTab tabName="Notes" /> },
                  { path: "audit", element: <ContactAuditTab /> },
                ],
              },
              { path: "/enquiries", element: <EnquiriesListPage /> },
              {
                path: "/enquiries/:id",
                element: <EnquiryDetailLayout />,
                children: [
                  { index: true, element: <Navigate to="details" replace /> },
                  { path: "details", element: <EnquiryDetailsTab /> },
                  { path: "activity", element: <EnquiryActivityTab /> },
                  { path: "notes", element: <EnquiryNotesTab /> },
                ],
              },
              { path: "/quotations", element: <QuotationsListPage /> },
              { path: "/quotations/:id", element: <QuotationDetailLayout /> },
              { path: "/bookings", element: <BookingsListPage /> },
              {
                path: "/bookings/:id",
                element: <BookingDetailLayout />,
                children: [
                  { index: true, element: <Navigate to="overview" replace /> },
                  { path: "overview", element: <BookingOverviewTab /> },
                  { path: "timeline", element: <BookingTimelineTab /> },
                  { path: "notes", element: <BookingNotesTab /> },
                  { path: "payments", element: <BookingPaymentsTab /> },
                  { path: "concierge", element: <BookingConciergeTab /> },
                  { path: "finance", element: <BookingFinanceTab /> },
                  ...bookingPlaceholderRoutes,
                ],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
