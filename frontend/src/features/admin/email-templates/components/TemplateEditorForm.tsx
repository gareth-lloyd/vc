import { useEffect, useMemo, useState } from "react";
import { Controller, useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { CodeField } from "./CodeField";
import { PreviewPane, type PreviewDraft } from "./PreviewPane";
import { TestSendDialog } from "./TestSendDialog";
import { usePublishEmailTemplate } from "../hooks";
import {
  emailTemplateCreateInputSchema,
  emailTemplatePublishInputSchema,
  type EmailTemplateCreateInput,
  type EmailTemplateDetail,
} from "../schemas";

type Props = { mode: "create" } | { mode: "edit"; template: EmailTemplateDetail };

// The form always carries `key` (hidden in edit mode); the publish payload
// strips it since the key is addressed in the URL, not the body.
const CREATE_DEFAULTS: EmailTemplateCreateInput = {
  key: "",
  title: "",
  subject_template: "",
  body_template_mjml: "",
  notes: "",
};

function editDefaults(template: EmailTemplateDetail): EmailTemplateCreateInput {
  return {
    key: template.key,
    title: template.title,
    subject_template: template.subject_template,
    body_template_mjml: template.body_template_mjml,
    notes: template.notes,
  };
}

const FORM_FIELDS = ["key", "title", "subject_template", "body_template_mjml", "notes"] as const;

export function TemplateEditorForm(props: Props) {
  const { t } = useTranslation("admin");
  const navigate = useNavigate();
  const isCreate = props.mode === "create";
  const canWrite = useHasAdminRole();
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [testSendOpen, setTestSendOpen] = useState(false);

  const form = useForm<EmailTemplateCreateInput>({
    // The edit-mode (publish) schema validates a subset of the form fields —
    // `key` is hidden and ignored there — so the resolver types don't overlap;
    // the form is uniformly typed as the create input and `key` is dropped from
    // the publish payload.
    resolver: zodResolver(
      isCreate ? emailTemplateCreateInputSchema : emailTemplatePublishInputSchema,
    ) as unknown as Resolver<EmailTemplateCreateInput>,
    defaultValues: isCreate ? CREATE_DEFAULTS : editDefaults(props.template),
  });

  // Re-seed when navigating between templates (edit mode) without unmounting.
  const editKey = isCreate ? null : props.template.key;
  useEffect(() => {
    form.reset(isCreate ? CREATE_DEFAULTS : editDefaults(props.template));
    setTopLevelError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editKey]);

  // The key the publish/preview calls address. Edit is fixed; create follows
  // the typed `key` field so the live preview works as soon as a key exists.
  const watchedKey = form.watch("key");
  const effectiveKey = isCreate ? watchedKey.trim() : props.template.key;
  const publish = usePublishEmailTemplate(effectiveKey);

  // Debounce the previewable fields *and* the key together, so typing the key in
  // create mode doesn't fire a preview POST per keystroke against partial keys.
  const subject = form.watch("subject_template");
  const mjml = form.watch("body_template_mjml");
  const [debounced, setDebounced] = useState<{ key: string; draft: PreviewDraft }>({
    key: effectiveKey,
    draft: { subject_template: subject, body_template_mjml: mjml },
  });
  useEffect(() => {
    const handle = setTimeout(
      () =>
        setDebounced({
          key: effectiveKey,
          draft: { subject_template: subject, body_template_mjml: mjml },
        }),
      350,
    );
    return () => clearTimeout(handle);
  }, [effectiveKey, subject, mjml]);

  const submitLabel = useMemo(
    () => (isCreate ? t("email_templates.form.create_submit") : t("email_templates.form.publish")),
    [isCreate, t],
  );

  const handleSubmit = async (values: EmailTemplateCreateInput) => {
    setTopLevelError(null);
    try {
      const published = await publish.mutateAsync({
        title: values.title,
        subject_template: values.subject_template,
        body_template_mjml: values.body_template_mjml,
        notes: values.notes || undefined,
      });
      if (isCreate) {
        toast.success(t("email_templates.toasts.created"));
        navigate(`/admin/email-templates/${encodeURIComponent(published.key)}`);
      } else {
        toast.success(t("email_templates.toasts.published"));
      }
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        // `body_template_html` is a server-derived field with no form input, so
        // its compile errors have nowhere inline to land — surface them (and any
        // other unmapped field error) in the top-level alert.
        const extra = Object.entries(error.fieldErrors)
          .filter(([f]) => !FORM_FIELDS.includes(f as (typeof FORM_FIELDS)[number]))
          .flatMap(([, messages]) => messages);
        setTopLevelError([detail, ...extra].filter(Boolean).join(" ") || null);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
        {isCreate ? (
          <div className="space-y-2">
            <Label htmlFor="tmpl-key">{t("email_templates.form.fields.key")}</Label>
            <Input id="tmpl-key" {...form.register("key")} className="font-mono" />
            <p className="text-muted-foreground text-xs">{t("email_templates.form.key_help")}</p>
            {form.formState.errors.key ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.key.message}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-2">
          <Label htmlFor="tmpl-title">{t("email_templates.form.fields.title")}</Label>
          <Input id="tmpl-title" {...form.register("title")} />
          {form.formState.errors.title ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.title.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="tmpl-subject">{t("email_templates.form.fields.subject_template")}</Label>
          <Input id="tmpl-subject" {...form.register("subject_template")} />
          {form.formState.errors.subject_template ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.subject_template.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label>{t("email_templates.form.fields.body_template_mjml")}</Label>
          <Controller
            control={form.control}
            name="body_template_mjml"
            render={({ field }) => (
              <CodeField
                value={field.value ?? ""}
                onChange={field.onChange}
                ariaLabel={t("email_templates.form.fields.body_template_mjml")}
                language="html"
              />
            )}
          />
          <p className="text-muted-foreground text-xs">{t("email_templates.form.mjml_help")}</p>
          {form.formState.errors.body_template_mjml ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.body_template_mjml.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="tmpl-notes">{t("email_templates.form.fields.notes")}</Label>
          <Textarea id="tmpl-notes" rows={2} {...form.register("notes")} />
        </div>

        <FormErrorAlert message={topLevelError} />

        <div className="flex flex-wrap justify-end gap-2">
          {!isCreate ? (
            <Button
              type="button"
              variant="secondary"
              onClick={() => setTestSendOpen(true)}
              disabled={!canWrite}
            >
              {t("email_templates.test_send.button")}
            </Button>
          ) : null}
          <Button type="submit" disabled={!canWrite || publish.isPending}>
            {publish.isPending ? t("email_templates.form.publishing") : submitLabel}
          </Button>
        </div>
      </form>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("email_templates.preview.heading")}
        </p>
        <PreviewPane mode="live" templateKey={debounced.key} draft={debounced.draft} enabled />
      </div>

      {!isCreate && testSendOpen ? (
        <TestSendDialog
          templateKey={props.template.key}
          open={testSendOpen}
          onOpenChange={setTestSendOpen}
        />
      ) : null}
    </div>
  );
}
