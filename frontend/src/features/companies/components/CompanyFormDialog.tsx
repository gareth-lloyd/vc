import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { ApiError } from "@/lib/api/errors";
import type { CompanyId } from "@/lib/query/keys";
import { useCreateCompany, useUpdateCompany } from "../hooks";
import {
  companyCreateInputSchema,
  companyWriteInputSchema,
  type Company,
  type CompanyWriteInput,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
  // Called after a successful create so a consumer (e.g. the contact form) can
  // auto-select the newly minted agency.
  onCreated?: (company: Company) => void;
}

interface EditProps extends CommonProps {
  mode: "edit";
  companyId: CompanyId;
  company: Company;
}

type CompanyFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: CompanyWriteInput = {
  name: "",
  email: "",
  phone: "",
  address_line_1: "",
  address_line_2: "",
  town: "",
  post_code: "",
  website_url: "",
  notes: "",
};

function defaultsFromCompany(c: Company): CompanyWriteInput {
  return {
    name: c.name ?? "",
    email: c.email ?? "",
    phone: c.phone ?? "",
    address_line_1: c.address_line_1 ?? "",
    address_line_2: c.address_line_2 ?? "",
    town: c.town ?? "",
    post_code: c.post_code ?? "",
    website_url: c.website_url ?? "",
    notes: c.notes ?? "",
  };
}

export function CompanyFormDialog(props: CompanyFormDialogProps) {
  const { t } = useTranslation("companies");
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const resolver = (
    isCreate ? zodResolver(companyCreateInputSchema) : zodResolver(companyWriteInputSchema)
  ) as Resolver<CompanyWriteInput>;

  const form = useForm<CompanyWriteInput>({
    resolver,
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromCompany(props.company),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateCompany();
  const updateMutation = useUpdateCompany(isCreate ? 0 : props.companyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromCompany(props.company));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.companyId]);

  const handleSubmit = async (values: CompanyWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        // org_type is stamped by createCompany (the directory only mints agencies).
        const created = await createMutation.mutateAsync(values);
        toast.success(t("toasts.created"));
        props.onCreated?.(created);
      } else {
        await updateMutation.mutateAsync(values);
        toast.success(t("toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("headings.create_dialog") : t("headings.edit_dialog")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="company-name">{t("fields.name")}</Label>
            <Input id="company-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="company-email">{t("fields.email")}</Label>
              <Input
                id="company-email"
                type="email"
                placeholder={t("placeholders.email")}
                {...form.register("email")}
              />
              {form.formState.errors.email ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.email.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="company-phone">{t("fields.phone")}</Label>
              <Input
                id="company-phone"
                placeholder={t("placeholders.phone")}
                {...form.register("phone")}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="company-address-1">{t("fields.address_line_1")}</Label>
            <Input id="company-address-1" {...form.register("address_line_1")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="company-address-2">{t("fields.address_line_2")}</Label>
            <Input id="company-address-2" {...form.register("address_line_2")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="company-town">{t("fields.town")}</Label>
              <Input id="company-town" {...form.register("town")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="company-post-code">{t("fields.post_code")}</Label>
              <Input id="company-post-code" {...form.register("post_code")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="company-website">{t("fields.website")}</Label>
            <Input id="company-website" {...form.register("website_url")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="company-notes">{t("fields.notes")}</Label>
            <Textarea id="company-notes" rows={3} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("common:actions.saving")
                : isCreate
                  ? t("actions.create")
                  : t("common:actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
