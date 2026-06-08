import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ContextSourcePicker } from "./ContextSourcePicker";
import { useEmailTemplatePreview } from "../hooks";
import { contextToRequest, type ContextSource, type TemplatePreviewRequest } from "../schemas";

// The draft fields the live preview re-renders against. Already debounced by the
// parent so each keystroke doesn't refire the (MJML-recompiling) request.
export interface PreviewDraft {
  subject_template: string;
  body_template_mjml?: string;
}

type PreviewPaneProps =
  | { mode: "live"; templateKey: string; draft: PreviewDraft; enabled: boolean }
  | { mode: "static"; subject: string; html: string; text?: string };

function PreviewFrame({ subject, html, text }: { subject: string; html: string; text?: string }) {
  const { t } = useTranslation("admin");
  return (
    <div className="space-y-3">
      <div>
        <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("email_templates.preview.subject_label")}
        </p>
        <p className="text-sm font-medium">{subject}</p>
      </div>
      <iframe
        title={t("email_templates.preview.iframe_title")}
        srcDoc={html}
        sandbox=""
        className="border-border h-96 w-full rounded-md border bg-white"
      />
      {text ? (
        <pre className="text-muted-foreground max-h-40 overflow-auto text-xs">{text}</pre>
      ) : null}
    </div>
  );
}

// Live, debounced preview with a context-source picker. For the read-only
// version view (`mode="static"`) it just renders the already-compiled HTML.
export function PreviewPane(props: PreviewPaneProps) {
  if (props.mode === "static") {
    return <PreviewFrame subject={props.subject} html={props.html} />;
  }
  return <LivePreview {...props} />;
}

function LivePreview({
  templateKey,
  draft,
  enabled,
}: {
  templateKey: string;
  draft: PreviewDraft;
  enabled: boolean;
}) {
  const { t } = useTranslation("admin");
  const [source, setSource] = useState<ContextSource>({ kind: "none" });
  const handleSource = useCallback((next: ContextSource) => setSource(next), []);

  const request = useMemo<TemplatePreviewRequest>(
    () => ({ ...draft, ...contextToRequest(source) }),
    [draft, source],
  );

  // Only fetch once there's a usable key (create mode starts keyless).
  const fetchEnabled = enabled && templateKey.length > 0;
  const preview = useEmailTemplatePreview(templateKey, fetchEnabled, request);

  return (
    <div className="space-y-4">
      <ContextSourcePicker onChange={handleSource} />

      {!fetchEnabled ? (
        <p className="text-muted-foreground text-sm">{t("email_templates.preview.empty")}</p>
      ) : preview.isError ? (
        <ErrorState
          description={t("email_templates.preview.error")}
          onRetry={() => preview.refetch()}
          retrying={preview.isFetching}
        />
      ) : !preview.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <PreviewFrame
          subject={preview.data.rendered_subject}
          html={preview.data.rendered_body_html}
          text={preview.data.rendered_body_text}
        />
      )}
    </div>
  );
}
