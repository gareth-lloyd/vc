import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { OwnerShell } from "@/features/owner-portal/OwnerShell";
import { RequireOwner } from "@/features/owner-portal/RequireOwner";
import { RequireAdmin, RequireAuth, RequireStaff } from "./guards";
import { BootGate } from "./boot";
import { RouteErrorBoundary } from "./RouteErrorBoundary";
import { LoginPage } from "@/features/auth/LoginPage";
import { TfaChallengePage } from "@/features/auth/TfaChallengePage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";
import {
  QuotationDetailRedirect,
  QuotationNewRedirect,
} from "@/features/quotations/routeRedirects";
import { NotFoundPage } from "./NotFoundPage";
import { PROPERTY_TABS } from "@/features/properties/tabConfig";
import { BOOKING_TABS } from "@/features/bookings/tabConfig";

const REAL_PROPERTY_TABS = new Set<string>([
  "details",
  "rooms",
  "nearby",
  "features",
  "pricing",
  "people",
  "availability",
  "media",
  "settings",
  "history",
]);
const propertyPlaceholderRoutes = PROPERTY_TABS.filter((t) => !REAL_PROPERTY_TABS.has(t.slug)).map(
  (t) => ({
    path: t.slug,
    element: <ComingSoonTab tabNameKey={`properties:${t.labelKey}`} />,
  }),
);

const REAL_BOOKING_TABS = new Set<string>([
  "overview",
  "timeline",
  "notes",
  "payments",
  "concierge",
  "finance",
  "owner",
  "comms",
  "history",
]);
const bookingPlaceholderRoutes = BOOKING_TABS.filter((t) => !REAL_BOOKING_TABS.has(t.slug)).map(
  (t) => ({
    path: t.slug,
    element: <ComingSoonTab tabNameKey={`bookings:${t.labelKey}`} />,
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
            element: <RequireOwner />,
            children: [
              {
                element: <OwnerShell />,
                errorElement: <RouteErrorBoundary />,
                children: [
                  { path: "/owner", element: <Navigate to="/owner/dashboard" replace /> },
                  {
                    path: "/owner/dashboard",
                    lazy: async () => {
                      const m = await import("@/features/owner-portal/OwnerDashboardPage");
                      return { Component: m.OwnerDashboardPage };
                    },
                  },
                  {
                    path: "/owner/properties",
                    lazy: async () => {
                      const m = await import("@/features/owner-portal/OwnerPropertiesPage");
                      return { Component: m.OwnerPropertiesPage };
                    },
                  },
                  {
                    path: "/owner/properties/:id/calendar",
                    lazy: async () => {
                      const m = await import("@/features/owner-portal/OwnerPropertyCalendarPage");
                      return { Component: m.OwnerPropertyCalendarPage };
                    },
                  },
                  {
                    path: "/owner/bookings",
                    lazy: async () => {
                      const m = await import("@/features/owner-portal/OwnerBookingsPage");
                      return { Component: m.OwnerBookingsPage };
                    },
                  },
                  {
                    path: "/owner/bookings/:id",
                    lazy: async () => {
                      const m = await import("@/features/owner-portal/OwnerBookingDetailPage");
                      return { Component: m.OwnerBookingDetailPage };
                    },
                  },
                ],
              },
            ],
          },
          {
            element: <RequireStaff />,
            children: [
              {
                element: <AppShell />,
                children: [
                  {
                    element: <Outlet />,
                    errorElement: <RouteErrorBoundary />,
                    children: [
                      { path: "/dashboard", element: <DashboardPage /> },
                      {
                        path: "/availability",
                        lazy: async () => {
                          const m =
                            await import("@/features/availability/AvailabilityTimelinePage");
                          return { Component: m.AvailabilityTimelinePage };
                        },
                      },
                      {
                        path: "/properties",
                        lazy: async () => {
                          const m = await import("@/features/properties/PropertiesListPage");
                          return { Component: m.PropertiesListPage };
                        },
                      },
                      {
                        path: "/properties/:id",
                        lazy: async () => {
                          const m = await import("@/features/properties/PropertyDetailLayout");
                          return { Component: m.PropertyDetailLayout };
                        },
                        children: [
                          { index: true, element: <Navigate to="details" replace /> },
                          {
                            path: "details",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/DetailsTab");
                              return { Component: m.DetailsTab };
                            },
                          },
                          {
                            path: "rooms",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/RoomsTab");
                              return { Component: m.RoomsTab };
                            },
                          },
                          {
                            path: "nearby",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/NearbyTab");
                              return { Component: m.NearbyTab };
                            },
                          },
                          {
                            path: "pricing",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/PricingTab");
                              return { Component: m.PricingTab };
                            },
                          },
                          {
                            path: "people",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/PeopleTab");
                              return { Component: m.PeopleTab };
                            },
                          },
                          {
                            path: "availability",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/AvailabilityTab");
                              return { Component: m.AvailabilityTab };
                            },
                          },
                          {
                            path: "media",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/MediaTab");
                              return { Component: m.MediaTab };
                            },
                          },
                          {
                            path: "features",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/FeaturesTab");
                              return { Component: m.FeaturesTab };
                            },
                          },
                          {
                            path: "settings",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/SettingsTab");
                              return { Component: m.SettingsTab };
                            },
                          },
                          {
                            path: "history",
                            lazy: async () => {
                              const m = await import("@/features/properties/tabs/HistoryTab");
                              return { Component: m.HistoryTab };
                            },
                          },
                          ...propertyPlaceholderRoutes,
                        ],
                      },
                      {
                        path: "/contacts",
                        lazy: async () => {
                          const m = await import("@/features/contacts/ContactsListPage");
                          return { Component: m.ContactsListPage };
                        },
                      },
                      {
                        path: "/contacts/:id",
                        lazy: async () => {
                          const m = await import("@/features/contacts/ContactDetailLayout");
                          return { Component: m.ContactDetailLayout };
                        },
                        children: [
                          { index: true, element: <Navigate to="details" replace /> },
                          {
                            path: "details",
                            lazy: async () => {
                              const m = await import("@/features/contacts/tabs/DetailsTab");
                              return { Component: m.DetailsTab };
                            },
                          },
                          {
                            path: "properties",
                            lazy: async () => {
                              const m = await import("@/features/contacts/tabs/PropertiesTab");
                              return { Component: m.PropertiesTab };
                            },
                          },
                          { path: "notes", element: <ComingSoonTab tabName="Notes" /> },
                          {
                            path: "audit",
                            lazy: async () => {
                              const m = await import("@/features/contacts/tabs/AuditTab");
                              return { Component: m.AuditTab };
                            },
                          },
                        ],
                      },
                      {
                        // Section layout mounts the Enquiries↔Quotes tab strip
                        // once above the active child (list/board or quotes).
                        path: "/enquiries",
                        lazy: async () => {
                          const m = await import("@/features/enquiries/EnquiriesSectionLayout");
                          return { Component: m.EnquiriesSectionLayout };
                        },
                        children: [
                          {
                            index: true,
                            lazy: async () => {
                              const m = await import("@/features/enquiries/EnquiriesListPage");
                              return { Component: m.EnquiriesListPage };
                            },
                          },
                          {
                            // Static segment ranks ahead of `/enquiries/:id`; the
                            // cross-enquiry quotes pipeline lives here as a tab.
                            path: "quotes",
                            lazy: async () => {
                              const m = await import("@/features/quotations/QuotationsTab");
                              return { Component: m.QuotationsTab };
                            },
                          },
                        ],
                      },
                      {
                        // Sibling of the section layout — the enquiry workspace
                        // carries no section tab strip.
                        path: "/enquiries/:id",
                        lazy: async () => {
                          const m = await import("@/features/enquiries/EnquiryDetailLayout");
                          return { Component: m.EnquiryDetailLayout };
                        },
                      },
                      {
                        // Quote detail nested under the Enquiries IA so the
                        // sidebar's Enquiries item stays highlighted and the URL
                        // matches the breadcrumb. Sibling of the section layout —
                        // a detail page, so no section tab strip. Static "quotes"
                        // ranks ahead of `/enquiries/:id`.
                        path: "/enquiries/quotes/:id",
                        lazy: async () => {
                          const m = await import("@/features/quotations/QuotationDetailLayout");
                          return { Component: m.QuotationDetailLayout };
                        },
                      },
                      // The Details/Activity/Notes tabs collapsed into the single
                      // enquiry workspace; redirect the old deep links (bookmarks,
                      // activity-timeline references) to the unified page.
                      {
                        path: "/enquiries/:id/details",
                        element: <Navigate to=".." relative="path" replace />,
                      },
                      {
                        path: "/enquiries/:id/activity",
                        element: <Navigate to=".." relative="path" replace />,
                      },
                      {
                        path: "/enquiries/:id/notes",
                        element: <Navigate to=".." relative="path" replace />,
                      },
                      // Standalone Quotes IA removed — the pipeline + detail now
                      // live under the Enquiries section and quote creation is
                      // inline in the enquiry workspace. Redirect old bookmarks
                      // to their IA-nested homes (ids/intent preserved).
                      {
                        path: "/quotations",
                        element: <Navigate to="/enquiries/quotes" replace />,
                      },
                      {
                        path: "/quotations/new",
                        element: <QuotationNewRedirect />,
                      },
                      {
                        path: "/quotations/:id",
                        element: <QuotationDetailRedirect />,
                      },
                      {
                        path: "/bookings",
                        lazy: async () => {
                          const m = await import("@/features/bookings/BookingsListPage");
                          return { Component: m.BookingsListPage };
                        },
                      },
                      {
                        path: "/concierge",
                        lazy: async () => {
                          const m = await import("@/features/concierge/ConciergeOverviewPage");
                          return { Component: m.ConciergeOverviewPage };
                        },
                      },
                      {
                        path: "/owner-blocks",
                        lazy: async () => {
                          const m =
                            await import("@/features/owner-block-updates/OwnerBlockUpdatesPage");
                          return { Component: m.OwnerBlockUpdatesPage };
                        },
                      },
                      {
                        element: <RequireAdmin />,
                        children: [
                          {
                            path: "/admin/users",
                            lazy: async () => {
                              const m = await import("@/features/admin/users/UsersAdminPage");
                              return { Component: m.UsersAdminPage };
                            },
                          },
                          {
                            path: "/admin/countries",
                            lazy: async () => {
                              const m =
                                await import("@/features/admin/countries/CountriesAdminPage");
                              return { Component: m.CountriesAdminPage };
                            },
                          },
                          {
                            path: "/admin/currencies",
                            lazy: async () => {
                              const m =
                                await import("@/features/admin/currencies/CurrenciesAdminPage");
                              return { Component: m.CurrenciesAdminPage };
                            },
                          },
                          {
                            path: "/admin/tags",
                            lazy: async () => {
                              const m = await import("@/features/admin/tags/TagsAdminPage");
                              return { Component: m.TagsAdminPage };
                            },
                          },
                          {
                            path: "/admin/email-templates",
                            lazy: async () => {
                              const m =
                                await import("@/features/admin/email-templates/EmailTemplatesListPage");
                              return { Component: m.EmailTemplatesListPage };
                            },
                          },
                          {
                            // Static `new` is matched ahead of the `:key` param.
                            path: "/admin/email-templates/new",
                            lazy: async () => {
                              const m =
                                await import("@/features/admin/email-templates/EmailTemplateEditorPage");
                              return { Component: m.EmailTemplateEditorPage };
                            },
                          },
                          {
                            path: "/admin/email-templates/:key",
                            lazy: async () => {
                              const m =
                                await import("@/features/admin/email-templates/EmailTemplateDetailLayout");
                              return { Component: m.EmailTemplateDetailLayout };
                            },
                            children: [
                              { index: true, element: <Navigate to="edit" replace /> },
                              {
                                path: "edit",
                                lazy: async () => {
                                  const m =
                                    await import("@/features/admin/email-templates/tabs/EditTab");
                                  return { Component: m.EditTab };
                                },
                              },
                              {
                                path: "versions",
                                lazy: async () => {
                                  const m =
                                    await import("@/features/admin/email-templates/tabs/VersionsTab");
                                  return { Component: m.VersionsTab };
                                },
                              },
                            ],
                          },
                          {
                            path: "/admin/system",
                            lazy: async () => {
                              const m = await import("@/features/admin/system/SystemAdminPage");
                              return { Component: m.SystemAdminPage };
                            },
                          },
                        ],
                      },
                      {
                        path: "/bookings/:id",
                        lazy: async () => {
                          const m = await import("@/features/bookings/BookingDetailLayout");
                          return { Component: m.BookingDetailLayout };
                        },
                        children: [
                          { index: true, element: <Navigate to="overview" replace /> },
                          {
                            path: "overview",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/OverviewTab");
                              return { Component: m.OverviewTab };
                            },
                          },
                          {
                            path: "timeline",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/TimelineTab");
                              return { Component: m.TimelineTab };
                            },
                          },
                          {
                            path: "notes",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/NotesTab");
                              return { Component: m.NotesTab };
                            },
                          },
                          {
                            path: "payments",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/PaymentsTab");
                              return { Component: m.PaymentsTab };
                            },
                          },
                          {
                            path: "concierge",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/ConciergeTab");
                              return { Component: m.ConciergeTab };
                            },
                          },
                          {
                            path: "finance",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/FinanceTab");
                              return { Component: m.FinanceTab };
                            },
                          },
                          {
                            path: "owner",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/OwnerTab");
                              return { Component: m.OwnerTab };
                            },
                          },
                          {
                            path: "comms",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/CommsTab");
                              return { Component: m.CommsTab };
                            },
                          },
                          {
                            path: "history",
                            lazy: async () => {
                              const m = await import("@/features/bookings/tabs/HistoryTab");
                              return { Component: m.HistoryTab };
                            },
                          },
                          ...bookingPlaceholderRoutes,
                        ],
                      },
                    ],
                  },
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
