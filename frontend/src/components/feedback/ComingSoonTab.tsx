import { useTranslation } from "react-i18next";
import { EmptyState } from "./EmptyState";

interface ComingSoonTabProps {
  /** Plain (already-resolved) tab name. Use this for back-compat with English literals. */
  tabName?: string;
  /**
   * Fully-qualified i18n key (e.g. `"properties:tabs.details"`). Resolved at render
   * time via `useTranslation` so the label updates on language switches.
   */
  tabNameKey?: string;
}

export function ComingSoonTab({ tabName, tabNameKey }: ComingSoonTabProps) {
  const { t } = useTranslation();
  const resolved = tabNameKey ? t(tabNameKey) : (tabName ?? "");
  return (
    <div className="p-6">
      <EmptyState
        title={`${resolved} — coming in next phase`}
        description={`This tab will be wired up in a future phase.`}
      />
    </div>
  );
}
