import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  fetchEmailTemplate,
  fetchEmailTemplates,
  fetchEmailTemplateVersions,
  previewEmailTemplate,
  publishEmailTemplate,
  testSendEmailTemplate,
} from "./api";
import type { EmailTemplateFilters, TemplatePreviewRequest, TestSendRequest } from "./schemas";

export function useEmailTemplates(filters: EmailTemplateFilters) {
  return useQuery({
    queryKey: queryKeys.emailTemplates.list(filters),
    queryFn: () => fetchEmailTemplates(filters),
  });
}

export function useEmailTemplate(key: string | undefined) {
  return useQuery({
    queryKey: key
      ? queryKeys.emailTemplates.detail(key)
      : ["email-templates", "detail", "__disabled__"],
    queryFn: () => fetchEmailTemplate(key as string),
    enabled: !!key,
  });
}

// PUT publishes a new version (in place on the same key); refresh the list, the
// active detail, and the version history.
export function usePublishEmailTemplate(key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      title: string;
      subject_template: string;
      body_template_mjml: string;
      notes?: string;
    }) => publishEmailTemplate(key, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.emailTemplates.lists() });
      qc.invalidateQueries({ queryKey: queryKeys.emailTemplates.detail(key) });
      qc.invalidateQueries({ queryKey: queryKeys.emailTemplates.versions(key) });
    },
  });
}

// Debounced live preview. Fired only while editing (`enabled`); `overrides`
// flow into both the request body and the query key so the rendered HTML
// re-fetches whenever the draft fields change. `keepPreviousData` keeps the
// last render on screen during a refetch so the iframe doesn't flash.
export function useEmailTemplatePreview(
  key: string,
  enabled: boolean,
  overrides: TemplatePreviewRequest,
) {
  return useQuery({
    queryKey: queryKeys.emailTemplates.preview(key, overrides),
    queryFn: () => previewEmailTemplate(key, overrides),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useTestSendEmailTemplate(key: string) {
  return useMutation({
    mutationFn: (body: TestSendRequest) => testSendEmailTemplate(key, body),
  });
}

export function useEmailTemplateVersions(key: string | undefined) {
  return useQuery({
    queryKey: key
      ? queryKeys.emailTemplates.versions(key)
      : ["email-templates", "detail", "__disabled__", "versions"],
    queryFn: () => fetchEmailTemplateVersions(key as string),
    enabled: !!key,
  });
}
