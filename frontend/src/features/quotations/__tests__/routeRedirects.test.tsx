import { Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { QuotationDetailRedirect, QuotationNewRedirect } from "../routeRedirects";

function DetailMarker() {
  const { id } = useParams();
  return <div>detail {id}</div>;
}
function WorkspaceMarker() {
  const { id } = useParams();
  return <div>workspace {id}</div>;
}

function harness(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/quotations/new" element={<QuotationNewRedirect />} />
      <Route path="/quotations/:id" element={<QuotationDetailRedirect />} />
      <Route path="/enquiries/quotes/:id" element={<DetailMarker />} />
      <Route path="/enquiries/quotes" element={<div>quotes pipeline</div>} />
      <Route path="/enquiries/:id" element={<WorkspaceMarker />} />
    </Routes>,
    { route },
  );
}

describe("quotation route redirects", () => {
  it("redirects /quotations/:id to the IA-nested detail, preserving the id", () => {
    harness("/quotations/55");
    expect(screen.getByText("detail 55")).toBeInTheDocument();
  });

  it("redirects /quotations/new?enquiry=5 to that enquiry's workspace", () => {
    harness("/quotations/new?enquiry=5");
    expect(screen.getByText("workspace 5")).toBeInTheDocument();
  });

  it("redirects bare /quotations/new to the quotes pipeline", () => {
    harness("/quotations/new");
    expect(screen.getByText("quotes pipeline")).toBeInTheDocument();
  });
});
