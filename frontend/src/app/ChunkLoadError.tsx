import { useEffect } from "react";
import { useRouteError } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

const CHUNK_FAILURE_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /Loading chunk \d+ failed/i,
  /ChunkLoadError/i,
];

function isChunkLoadError(error: unknown): boolean {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : typeof error === "object" && error !== null && "message" in error
          ? String((error as { message?: unknown }).message)
          : "";
  return CHUNK_FAILURE_PATTERNS.some((p) => p.test(message));
}

export function ChunkLoadError() {
  const error = useRouteError();
  const { t } = useTranslation("common");
  const chunk = isChunkLoadError(error);

  useEffect(() => {
    if (!chunk && import.meta.env.DEV) {
      console.error("Unhandled route error", error);
    }
  }, [chunk, error]);

  return (
    <div className="p-8">
      <div
        className="border-destructive/40 bg-destructive/5 rounded-lg border p-6 text-center"
        role="alert"
      >
        <h3 className="text-destructive text-base font-medium">
          {chunk ? t("errors.chunk_load_title") : t("errors.generic")}
        </h3>
        <p className="text-muted-foreground mt-1 text-sm">
          {chunk ? t("errors.chunk_load_body") : t("errors.couldnt_load")}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => window.location.reload()}
        >
          {t("actions.reload")}
        </Button>
      </div>
    </div>
  );
}
