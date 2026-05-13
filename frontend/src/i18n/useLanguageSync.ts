import { useEffect } from "react";
import i18n from "i18next";
import { useAuthStore } from "@/features/auth/store";
import { toSupportedLanguage } from "./normalize";

/**
 * Overlay the authenticated user's `preferred_language` onto i18next.
 * Anonymous fallback (localStorage → navigator.language) is handled by
 * i18next-browser-languagedetector at init time.
 */
export function useLanguageSync(): void {
  const backendLanguage = useAuthStore((state) => state.user?.preferred_language);

  useEffect(() => {
    if (!backendLanguage) return;
    const target = toSupportedLanguage(backendLanguage);
    if (i18n.language !== target) {
      void i18n.changeLanguage(target);
    }
  }, [backendLanguage]);
}
