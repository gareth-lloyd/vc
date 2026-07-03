import { http, HttpResponse } from "msw";
import { Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { PropertiesTab } from "../tabs/PropertiesTab";
import type { Contact } from "../schemas";

function renderTab(contact: Partial<Contact>) {
  const full = { id: 7, ...contact } as Contact;
  return renderWithProviders(
    <Routes>
      <Route path="/contacts/:id" element={<Outlet context={{ contact: full }} />}>
        <Route path="properties" element={<PropertiesTab />} />
        <Route path="details" element={<div>Details tab</div>} />
      </Route>
    </Routes>,
    { route: "/contacts/7/properties" },
  );
}

describe("PropertiesTab applicability guard", () => {
  it("redirects a pure client hitting the URL directly to the details tab", async () => {
    renderTab({ contact_types: ["customer"], has_property_assignments: false });
    await waitFor(() => expect(screen.getByText("Details tab")).toBeInTheDocument());
  });

  it("renders the assignments table for an owner", async () => {
    server.use(http.get("/api/v1/contacts/7/properties", () => HttpResponse.json([])));
    renderTab({ contact_types: ["owner"], has_property_assignments: true });
    expect(await screen.findByText("Property assignments")).toBeInTheDocument();
    expect(screen.queryByText("Details tab")).not.toBeInTheDocument();
  });
});
