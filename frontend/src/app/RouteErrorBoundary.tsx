import { useEffect } from "react";
import { useNavigate, useRouteError } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

const CHUNK_FAILURE_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /Loading chunk \d+ failed/i,
  /ChunkLoadError/i,
  /dynamically imported module/i,
];

function extractMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (typeof error === "object" && error !== null && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return "";
}

function isChunkLoadError(error: unknown): boolean {
  const message = extractMessage(error);
  return CHUNK_FAILURE_PATTERNS.some((p) => p.test(message));
}

export function RouteErrorBoundary() {
  const error = useRouteError();
  const navigate = useNavigate();
  const { t } = useTranslation("common");
  const chunk = isChunkLoadError(error);

  useEffect(() => {
    console.error("Route error caught by boundary", error);
  }, [error]);

  return (
    <div className="p-8">
      <div
        className="border-destructive/40 bg-destructive/5 rounded-lg border p-6 text-center"
        role="alert"
      >
        <h3 className="text-destructive text-base font-medium">
          {chunk ? t("errors.chunk_load_title") : t("errors.render_error_title")}
        </h3>
        <p className="text-muted-foreground mt-1 text-sm">
          {chunk ? t("errors.chunk_load_body") : t("errors.render_error_body")}
        </p>
        {chunk ? (
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => window.location.reload()}
          >
            {t("actions.reload")}
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => navigate("/dashboard")}
          >
            {t("actions.back_to_dashboard")}
          </Button>
        )}
      </div>
    </div>
  );
}
