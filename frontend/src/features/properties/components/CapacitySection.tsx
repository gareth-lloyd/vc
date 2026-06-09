import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { usePropertyCapacity, useUpdatePropertyCapacity } from "../hooks";
import {
  isCapacityUnset,
  propertyCapacityWriteInputSchema,
  type PropertyCapacity,
  type PropertyCapacityWriteInput,
} from "../schemas";

const INT_FIELDS = ["guests", "additional_guests", "bedrooms", "ensuites", "bathrooms"] as const;

function capacityDefaults(c: PropertyCapacity): PropertyCapacityWriteInput {
  return {
    guests: c.guests,
    additional_guests: c.additional_guests,
    bedrooms: c.bedrooms,
    ensuites: c.ensuites,
    bathrooms: c.bathrooms,
    size_sqm: c.size_sqm ?? "",
  };
}

function CapacityForm({
  propertyId,
  initial,
  canWrite,
}: {
  propertyId: number;
  initial: PropertyCapacity;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const form = useForm<PropertyCapacityWriteInput>({
    resolver: zodResolver(propertyCapacityWriteInputSchema),
    defaultValues: capacityDefaults(initial),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useUpdatePropertyCapacity(propertyId);

  useEffect(() => {
    form.reset(capacityDefaults(initial));
  }, [initial, form]);

  const onSubmit = async (values: PropertyCapacityWriteInput) => {
    setTopLevelError(null);
    try {
      const size = typeof values.size_sqm === "string" ? values.size_sqm.trim() : values.size_sqm;
      await mutation.mutateAsync({ ...values, size_sqm: size ? size : null });
      toast.success(t("details.capacity.saved"));
      form.reset(values);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("details.capacity.save_failed"));
      }
    }
  };

  const guests = form.watch("guests");

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <p className="text-muted-foreground text-sm">{t("details.capacity.description")}</p>

      {isCapacityUnset({ guests }) ? (
        <p
          className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
          role="status"
        >
          {t("details.capacity.warning_not_set")}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {INT_FIELDS.map((field) => (
          <div key={field} className="space-y-2">
            <Label htmlFor={`prop-capacity-${field}`}>
              {t(`details.capacity.fields.${field}`)}
            </Label>
            <Input
              id={`prop-capacity-${field}`}
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register(field, {
                setValueAs: (v) => (v === "" || v == null ? 0 : Number(v)),
              })}
            />
          </div>
        ))}

        <div className="space-y-2">
          <Label htmlFor="prop-capacity-size_sqm">{t("details.capacity.fields.size_sqm")}</Label>
          <Input
            id="prop-capacity-size_sqm"
            type="number"
            min={0}
            step="0.01"
            disabled={!canWrite}
            {...form.register("size_sqm")}
          />
        </div>
      </div>

      <FormErrorAlert message={topLevelError} fieldErrors={form.formState.errors} />

      <div className="flex justify-end">
        <Button type="submit" disabled={!canWrite || !form.formState.isDirty || mutation.isPending}>
          {mutation.isPending ? t("details.capacity.saving") : t("details.capacity.save")}
        </Button>
      </div>
    </form>
  );
}

export function CapacitySection({ propertyId }: { propertyId: number }) {
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const capacity = usePropertyCapacity(propertyId);

  if (capacity.isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (capacity.isError || !capacity.data) {
    return (
      <ErrorState
        title={t("details.capacity.error_title")}
        description={t("details.capacity.error_body")}
        onRetry={() => capacity.refetch()}
        retrying={capacity.isFetching}
      />
    );
  }

  return <CapacityForm propertyId={propertyId} initial={capacity.data} canWrite={canWrite} />;
}
