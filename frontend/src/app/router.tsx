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
import { BookingsListPage } from "@/features/bookings/BookingsListPage";
import { BOOKING_TABS, BookingDetailLayout } from "@/features/bookings/BookingDetailLayout";
import { OverviewTab as BookingOverviewTab } from "@/features/bookings/tabs/OverviewTab";
import { TimelineTab as BookingTimelineTab } from "@/features/bookings/tabs/TimelineTab";
import { NotesTab as BookingNotesTab } from "@/features/bookings/tabs/NotesTab";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";
import { NotFoundPage } from "./NotFoundPage";

const REAL_PROPERTY_TABS = new Set<string>(["details", "pricing", "people"]);
const propertyPlaceholderRoutes = PROPERTY_TABS.filter((t) => !REAL_PROPERTY_TABS.has(t.slug)).map(
  (t) => ({
    path: t.slug,
    element: <ComingSoonTab tabName={t.label} />,
  }),
);

const REAL_BOOKING_TABS = new Set<string>(["overview", "timeline", "notes"]);
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
                  ...propertyPlaceholderRoutes,
                ],
              },
              { path: "/bookings", element: <BookingsListPage /> },
              {
                path: "/bookings/:id",
                element: <BookingDetailLayout />,
                children: [
                  { index: true, element: <Navigate to="overview" replace /> },
                  { path: "overview", element: <BookingOverviewTab /> },
                  { path: "timeline", element: <BookingTimelineTab /> },
                  { path: "notes", element: <BookingNotesTab /> },
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
