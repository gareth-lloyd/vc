import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { z } from "zod";
import { zodErrorMap } from "./zodErrorMap";

import commonEn from "./locales/en/common.json";
import authEn from "./locales/en/auth.json";
import contactsEn from "./locales/en/contacts.json";
import propertiesEn from "./locales/en/properties.json";
import bookingsEn from "./locales/en/bookings.json";
import enquiriesEn from "./locales/en/enquiries.json";
import usersEn from "./locales/en/users.json";
import quotationsEn from "./locales/en/quotations.json";
import auditEn from "./locales/en/audit.json";
import adminEn from "./locales/en/admin.json";
import dashboardEn from "./locales/en/dashboard.json";

export const SUPPORTED_LANGUAGES = ["en"] as const;
export const DEFAULT_LANGUAGE: (typeof SUPPORTED_LANGUAGES)[number] = "en";

export const I18N_NAMESPACES = [
  "common",
  "auth",
  "contacts",
  "properties",
  "bookings",
  "enquiries",
  "users",
  "quotations",
  "audit",
  "admin",
  "dashboard",
] as const;

const supportedLngs: string[] = [...SUPPORTED_LANGUAGES];
const namespaces: string[] = [...I18N_NAMESPACES];

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: commonEn,
        auth: authEn,
        contacts: contactsEn,
        properties: propertiesEn,
        bookings: bookingsEn,
        enquiries: enquiriesEn,
        users: usersEn,
        quotations: quotationsEn,
        audit: auditEn,
        admin: adminEn,
        dashboard: dashboardEn,
      },
    },
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs,
    defaultNS: "common",
    ns: namespaces,
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "vc.lang",
      caches: ["localStorage"],
    },
    returnNull: false,
  });

z.setErrorMap(zodErrorMap);

declare global {
  interface Window {
    i18next?: typeof i18n;
  }
}

if (import.meta.env.DEV) {
  window.i18next = i18n;
}

export default i18n;
