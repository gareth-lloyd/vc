import { Navigate, useParams, useSearchParams } from "react-router-dom";

/**
 * Legacy `/quotations/:id` bookmark → the IA-nested detail route under the
 * Enquiries section, preserving the id. Quote detail moved under
 * `/enquiries/quotes/:id` so the sidebar's Enquiries item stays highlighted and
 * the URL matches the breadcrumb trail.
 */
export function QuotationDetailRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/enquiries/quotes/${id}`} replace />;
}

/**
 * Legacy `/quotations/new` link → the enquiry workspace (where the inline quote
 * builder lives, auto-expanded on a quote-less enquiry) when the originating
 * enquiry is known via `?enquiry=`, else the cross-enquiry quotes pipeline.
 * Honors the creation intent instead of dropping it on a read-only list.
 */
export function QuotationNewRedirect() {
  const [params] = useSearchParams();
  const enquiry = params.get("enquiry");
  return <Navigate to={enquiry ? `/enquiries/${enquiry}` : "/enquiries/quotes"} replace />;
}
