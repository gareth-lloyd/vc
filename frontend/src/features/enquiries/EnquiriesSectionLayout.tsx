import { Outlet } from "react-router-dom";
import { EnquiriesTabs } from "./components/EnquiriesTabs";

/**
 * Section layout for the Enquiries area: mounts the Enquiries↔Quotes tab strip
 * once, above whichever child route is active (the enquiry list/board at
 * `/enquiries`, or the cross-enquiry quotes pipeline at `/enquiries/quotes`) —
 * the same layout-route + `<Outlet>` shape as the detail layouts, so the strip
 * isn't re-rendered by each page. The enquiry workspace (`/enquiries/:id`) is a
 * sibling route, deliberately outside this layout — it carries no section strip.
 */
export function EnquiriesSectionLayout() {
  return (
    <div>
      <EnquiriesTabs />
      <Outlet />
    </div>
  );
}
