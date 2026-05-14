import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation("common");
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-semibold">{t("errors.not_found_title")}</h1>
      <p className="text-muted-foreground">{t("errors.not_found_body")}</p>
      <Button asChild>
        <Link to="/dashboard">{t("actions.back_to_dashboard")}</Link>
      </Button>
    </div>
  );
}
