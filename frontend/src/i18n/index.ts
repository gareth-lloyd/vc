import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { z } from "zod";
import { zodErrorMap } from "./zodErrorMap";

import commonEn from "./locales/en/common.json";
import authEn from "./locales/en/auth.json";
import contactsEn from "./locales/en/contacts.json";
import guestsEn from "./locales/en/guests.json";
import propertiesEn from "./locales/en/properties.json";
import bookingsEn from "./locales/en/bookings.json";
import enquiriesEn from "./locales/en/enquiries.json";
import usersEn from "./locales/en/users.json";
import quotationsEn from "./locales/en/quotations.json";
import auditEn from "./locales/en/audit.json";
import adminEn from "./locales/en/admin.json";
import dashboardEn from "./locales/en/dashboard.json";
import conciergeEn from "./locales/en/concierge.json";
import ownerEn from "./locales/en/owner.json";

import commonEl from "./locales/el/common.json";
import authEl from "./locales/el/auth.json";
import contactsEl from "./locales/el/contacts.json";
import guestsEl from "./locales/el/guests.json";
import propertiesEl from "./locales/el/properties.json";
import bookingsEl from "./locales/el/bookings.json";
import enquiriesEl from "./locales/el/enquiries.json";
import usersEl from "./locales/el/users.json";
import quotationsEl from "./locales/el/quotations.json";
import auditEl from "./locales/el/audit.json";
import adminEl from "./locales/el/admin.json";
import dashboardEl from "./locales/el/dashboard.json";
import conciergeEl from "./locales/el/concierge.json";
import ownerEl from "./locales/el/owner.json";

export const SUPPORTED_LANGUAGES = ["en", "el"] as const;
export const DEFAULT_LANGUAGE: (typeof SUPPORTED_LANGUAGES)[number] = "en";

// Autonyms — intentionally not run through t(): "Ελληνικά" must read
// "Ελληνικά" in any UI locale, so a user can find their language.
export const LANGUAGE_AUTONYMS: Record<(typeof SUPPORTED_LANGUAGES)[number], string> = {
  en: "English",
  el: "Ελληνικά",
};

export const I18N_NAMESPACES = [
  "common",
  "auth",
  "contacts",
  "guests",
  "properties",
  "bookings",
  "enquiries",
  "users",
  "quotations",
  "audit",
  "admin",
  "dashboard",
  "concierge",
  "owner",
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
        guests: guestsEn,
        properties: propertiesEn,
        bookings: bookingsEn,
        enquiries: enquiriesEn,
        users: usersEn,
        quotations: quotationsEn,
        audit: auditEn,
        admin: adminEn,
        dashboard: dashboardEn,
        concierge: conciergeEn,
        owner: ownerEn,
      },
      el: {
        common: commonEl,
        auth: authEl,
        contacts: contactsEl,
        guests: guestsEl,
        properties: propertiesEl,
        bookings: bookingsEl,
        enquiries: enquiriesEl,
        users: usersEl,
        quotations: quotationsEl,
        audit: auditEl,
        admin: adminEl,
        dashboard: dashboardEl,
        concierge: conciergeEl,
        owner: ownerEl,
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
