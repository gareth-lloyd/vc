import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { useEnquiry } from "@/features/enquiries/hooks";
import { QuoteBuilder } from "./components/QuoteBuilder";

export function QuotationBuilderPage() {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const enquiryParam = params.get("enquiry");
  const enquiryId = enquiryParam && /^\d+$/.test(enquiryParam) ? Number(enquiryParam) : undefined;

  const enquiryQuery = useEnquiry(enquiryId);
  const enquiry = enquiryQuery.data ?? null;

  if (enquiryQuery.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (enquiryId == null) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("builder.errors.no_enquiry_title")}
          description={t("builder.errors.no_enquiry_description")}
        />
      </div>
    );
  }

  if (enquiryQuery.isError || !enquiry) {
    const is404 = enquiryQuery.error instanceof ApiError && enquiryQuery.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={
            is404 ? t("builder.errors.enquiry_not_found") : t("builder.errors.enquiry_load_failed")
          }
          description={
            is404
              ? t("builder.errors.enquiry_not_found_description")
              : t("builder.errors.enquiry_load_failed_description")
          }
          onRetry={is404 ? undefined : () => enquiryQuery.refetch()}
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("builder.title")}
        subtitle={t("builder.subtitle", { reference: enquiry.reference })}
        breadcrumbs={[
          { label: t("detail.breadcrumb_root") },
          { label: t("detail.breadcrumb_list"), to: "/quotations" },
          { label: t("builder.breadcrumb_self") },
        ]}
      />

      <div className="px-6 py-6">
        <QuoteBuilder enquiry={enquiry} onComplete={(q) => navigate(`/quotations/${q.id}`)} />
      </div>
    </div>
  );
}
